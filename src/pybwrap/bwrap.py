import functools
import logging
import os
import socket
from textwrap import dedent
from enum import Enum
from glob import glob
from pathlib import Path
from typing import Callable, Optional, Self, TypedDict, Union, Unpack


class BindMode(Enum):
    RW = "rw"
    RO = "ro"
    DEV = "dev"


class Bwrap:
    _DEFAULT_ETC_BINDS = (
        "bash.bashrc", "bash_completion.d", "binfmt.d", "bluetooth",
        "ca-certificates", "conf.d", "dconf", "default", "environment",
        "ethertypes", "fonts", "fuse.conf", "gai.conf", "grc.conf", "grc.fish",
        "grc.zsh", "group", "gtk-2.0", "gtk-3.0", "host.conf", "inputrc",
        "issue", "java-openjdk", "ld.so.cache", "ld.so.conf", "ld.so.conf.d",
        "libao.conf", "libinput", "libnl", "libpaper.d", "libva.conf",
        "locale.conf", "localtime", "login.defs", "lsb-release", "man_db.conf",
        "mime.types", "mono", "mtab", "named.conf", "machine-id", "ndctl",
        "ndctl.conf.d", "odbc.ini", "odbcinst.ini", "openldap", "openmpi",
        "openpmix", "os-release", "pam.d", "papersize", "paru.conf", "pipewire",
        "pkcs11", "povray", "profile", "profile.d", "protocols", "pulse",
        "rc_keymaps", "rc_maps.cfg", "request-key.conf", "request-key.d",
        "resolv.conf", "sane.d", "sasl2", "securetty", "security", "sensors.d",
        "sensors3.conf", "services", "shells", "ssl", "subgid", "subuid",
        "timidity", "tmpfiles.d", "tpm2-tss", "trusted-key.key", "ts.conf",
        "vdpau_wrapper.cfg", "vulkan", "wgetrc", "whois.conf", "wpa_supplicant",
        "xattr.conf", "xdg", "xinetd.d", "xml", "libreoffice", "java21-openjdk",
        "java11-openjdk"
    )  # fmt: skip
    _DEFAULT_PATHS = (
        ".local/bin",
        "go/bin",
        "/usr/local/bin",
        "/usr/local/sbin",
        "/usr/bin",
        "/usr/sbin",
        "/bin",
        "/sbin",
    )

    class BwrapOptions(TypedDict):
        user: str
        hostname: str
        home: Optional[Path]
        etc_binds: tuple[str]
        loglevel: int
        path: Optional[tuple[str]]
        clearenv: bool
        keep_child: bool
        rootfs: Optional[Path]

    def __init__(self, **kwargs: Unpack[BwrapOptions]):
        self.logger = logging.getLogger("bwrap")
        self.logger.setLevel(kwargs.get("loglevel", logging.ERROR))
        self.user: str = kwargs.get("user", "user")
        self.home: Path = kwargs.get("home", Path("/home") / self.user)
        self.hostname: str = kwargs.get("hostname", f"sandbox-{os.getpid()}")
        self.etc_binds: tuple[str] = kwargs.get("etc_binds", self._DEFAULT_ETC_BINDS)
        self._host_home: Path = Path.home()
        self.logger.info(f"container HOME: {self.home}")

        # Adjusts the host's current working directory (CWD) for the container.
        self.cwd = Path.cwd()
        if self.cwd.is_relative_to(self._host_home):
            self.cwd = self.home / self.cwd.relative_to(self._host_home)
        self.logger.info(f"container CWD: {self.cwd}")

        self._init_container(kwargs.get("rootfs"), kwargs.get("keep_child", False))
        self._init_xdg()
        self._init_env(kwargs.get("path"), kwargs.get("clearenv", True))
        self._init_system_id()

    def _init_container(self, rootfs, keep_child):
        """Base system"""
        self.args: list[str] = [
            "--tmpfs", "/tmp",
            "--proc", "/proc",
            "--dev", "/dev",
            "--dir", "/etc",
            "--dir", "/var",
            "--dir", "/run",
            "--unsetenv", "TMUX",
        ]  # fmt: skip

        if rootfs is None:
            self.logger.info("Using host rootfs")
            self.bind_many(
                "/usr",
                "/opt",
                "/sys/block",
                "/sys/bus",
                "/sys/class",
                "/sys/dev",
                "/sys/devices",
                {"src": "/dev/fuse", "mode": BindMode.DEV},
                "/var/empty",
                "/var/cache/man",
                "/var/lib/alsa",
                "/run/systemd/resolve",
                *(f"/etc/{e}" for e in self.etc_binds),
            )
            self.symlink(
                ("/usr/lib", "/lib"),
                ("/usr/lib", "/lib64"),
                ("/usr/bin", "/bin"),
                ("/usr/bin", "/sbin"),
                ("/run", "/var/run"),
            )
        else:
            self.logger.info(f"Using {rootfs} as rootfs")
            # TODO: bind rootfs
            raise NotImplementedError()

        if not keep_child:
            self.logger.info("Container will be killed when bwrap terminates")
            self.args.append("--die-with-parent")

    def _init_xdg(self):
        self.xdg_runtime_dir = Path(f"/run/user/{os.getuid()}")
        self.xdg_config_home = self.home / ".config"
        self.xdg_cache_home = self.home / ".cache"
        self.xdg_data_home = self.home / ".local" / "share"
        self.xdg_state_home = self.home / ".local" / "state"
        self.dir(
            self.home,
            self.xdg_runtime_dir,
            self.xdg_cache_home,
            self.xdg_config_home,
            self.xdg_data_home,
            self.xdg_state_home,
            self.home / ".local" / "bin",
        )
        self.home_bind_many(
            ".config/user-dirs.dirs",
            ".config/user-dirs.locale",
        )

    def _init_env(self, path, clearenv):
        if clearenv:
            # Do not inherit host env
            self.logger.info("Environment variables cleared")
            self.args.append("--clearenv")

        path = path or tuple(
            p if Path(p).is_absolute() else str(self.home / p)
            for p in self._DEFAULT_PATHS
        )

        self.setenv(
            HOME=self.home,
            SANDBOX=1,
            PATH=str.join(":", path),
            LOGNAME=self.user,
            USER=self.user,
            HOSTNAME=self.hostname,
            XDG_RUNTIME_DIR=str(self.xdg_runtime_dir),
            XDG_CONFIG_HOME=str(self.xdg_config_home),
            XDG_CACHE_HOME=str(self.xdg_cache_home),
            XDG_DATA_HOME=str(self.xdg_data_home),
            XDG_STATE_HOME=str(self.xdg_state_home),
        )
        self.logger.info(f"set PATH to {path}")

        # inherit from parent process
        self.keepenv(
            "COLORTERM",
            "EDITOR",
            "LANG",
            "LC_ALL",
            "LC_TIME",
            "NO_AT_BRIDGE",
            "PAGER",
            "SHELL",
            "TERM",
            "WINEDEBUG",
            "WINEFSYNC",
            "XDG_BACKEND",
            "XDG_SEAT",
            "XDG_SESSION_CLASS",
            "XDG_SESSION_ID",
            "XDG_SESSION_TYPE",
        )

    def _init_system_id(self):
        """Initialize system identity, such as hostname and user name"""
        if socket.gethostname() != self.hostname:
            self.logger.info(f"Hostname changed to {self.hostname}")
            self.args.extend([
                "--unshare-uts",
                "--hostname", self.hostname
            ])  # fmt: skip
        hosts_file = dedent(f"""
            127.0.0.1       localhost       localhost.localdomain
            ::1             localhost       localhost.localdomain
            127.0.0.1       {self.hostname}      {self.hostname}.localdomain
            ::1             {self.hostname}      {self.hostname}.localdomain
            127.0.0.1       {self.hostname}.local
        """)

        self.logger.info(f"User name changed to {self.user}")
        passwd_file = dedent(f"""
            root:x:0:0::/root:/usr/bin/bash
            bin:x:1:1::/:/usr/bin/nologin
            daemon:x:2:2::/:/usr/bin/nologin
            nobody:x:65534:65534:Kernel Overflow User:/:/usr/bin/nologin
            dbus:x:81:81:System Message Bus:/:/usr/bin/nologin
            polkitd:x:102:102:User for polkitd:/:/usr/bin/nologin
            {self.user}:x:{os.getuid()}:{os.getgid()}::{self.home}:{os.getenv("SHELL")}
        """)

        nsswitch_file = dedent("""
            passwd: files
            group: files [SUCCESS=merge] systemd
            shadow: files
            gshadow: files
            publickey: files
            hosts: mymachines files myhostname dns
            networks: files
            protocols: files
            services: files
            ethers: files
            rpc: files
            netgroup: files
        """)

        self.file(nsswitch_file, "/etc/nsswitch.conf")
        self.file(passwd_file, "/etc/passwd")
        self.file(hosts_file, "/etc/hosts")
        self.file(self.hostname, "/etc/hostname")

    @staticmethod
    def format_bind_args(src, dest, mode):
        """Format bind arguments based on binding mode"""
        return {
            BindMode.RW: ("--bind-try", str(src), str(dest)),
            BindMode.RO: ("--ro-bind-try", str(src), str(dest)),
            BindMode.DEV: ("--dev-bind-try", str(src), str(dest)),
        }[mode]

    def symlink(self, *symlink_spec: tuple[str]):
        for src, dest in symlink_spec:
            self.args.extend(["--symlink", str(src), str(dest)])

    def bind(self, src: str, dest: Optional[str] = None, mode: BindMode = BindMode.RO):
        dest: Path = Path(dest or src)
        # dest relative to CWD
        if not dest.is_absolute():
            self.logger.debug("bind: dest relative to host cwd")
            dest = self.cwd / dest
        # dest contains host home
        if dest.is_relative_to(self._host_home):
            self.logger.debug("bind: dest relative to host home")
            dest = self.home / dest.relative_to(self._host_home)

        self.args.extend(self.format_bind_args(src, str(dest), mode))

    def bind_many(self, *bind_specs: Union[str, dict], mode=BindMode.RO):
        for spec in bind_specs:
            if isinstance(spec, str):
                self.bind(spec, mode=mode)
            elif isinstance(spec, dict):
                self.bind(**spec)

    def home_bind(
        self, src: str, dest: Optional[str] = None, mode: BindMode = BindMode.RO
    ):
        """Bind directories under $HOME

        Args:
            src (Path): Relative path to host home, or absolute path
            dest (Optional[Path], optional): Must be a relative path to container home, Defaults to src
            mode (BindMode, optional): Defaults to read only
        """
        host_src = Path(src)
        if not host_src.is_absolute():
            host_src = self._host_home / src
        dest = dest or src
        assert not Path(dest).is_absolute()
        sandbox_dest = self.home / dest
        self.bind(host_src, sandbox_dest, mode)

    def home_bind_many(self, *bind_specs: Union[str, dict], mode=BindMode.RO):
        for spec in bind_specs:
            if isinstance(spec, str):
                self.home_bind(spec, mode=mode)
            elif isinstance(spec, dict):
                self.home_bind(**spec)

    def dir(self, *dirs: str):
        for dir in dirs:
            self.args.extend(("--dir", str(dir)))

    def tmpfs(self, *paths: str):
        for fs in paths:
            self.args.extend(("--tmpfs", str(fs)))

    def file(self, content: str, dest: str, perms=None):
        """Copy from file descriptor to dest

        Default permission is 0666
        """
        if perms:
            self.args.extend(("--perms", str(perms)))
        r, w = os.pipe()
        os.set_inheritable(r, True)
        os.write(w, content.encode())
        self.args.extend(("--file", str(r), str(dest)))

    def setenv(self, **kwargs):
        for var, value in kwargs.items():
            if value is None or var == "LC_ALL":
                continue
            self.args.extend(("--setenv", var, str(value)))

    def unsetenv(self, *vars: str):
        for var in vars:
            self.args.extend(("--unsetenv", var))

    def clearenv(self):
        self.args.append("--clearenv")

    def keepenv(self, *vars: str):
        """Inherit environment variables from host"""
        for var in vars:
            value = os.getenv(var)
            if value is None:
                continue
            self.args.extend(("--setenv", var, value))

    def unshare(self, net=False):
        self.args.append("--unshare-all")
        if not net:
            self.args.append("--share-net")

    def _debug_print_args(self, command):
        if self.logger.level <= logging.DEBUG:
            args = self.args + command
            indices = [i for i, x in enumerate(args) if x.startswith("--")]
            for a in (
                " ".join(args[i:j]) for i, j in zip(indices, indices[1:] + [len(args)])
            ):
                self.logger.debug(f"arg: {a}")

    def exec(self, command: list):
        self._debug_print_args()
        arg_fd, w = os.pipe()
        os.set_inheritable(arg_fd, True)
        os.write(w, "\0".join(self.args).encode())
        os.execvp("bwrap", ["bwrap", "--args", str(arg_fd)] + command)


class BwrapSandbox(Bwrap):
    def __init__(self, *args, **kwargs: Unpack[Bwrap.BwrapOptions]):
        super().__init__(*args, **kwargs)
        self._enabled_features = set()

    def feature(depends: tuple[str] = ()):
        def decorator(func: Callable):
            @functools.wraps(func)
            def wrapper(self: Self, *args, **kwargs):
                if func in self._enabled_features:
                    self.logger.info(
                        f"feature {func.__name__} is already enabled, skipping"
                    )
                    return
                self._enabled_features.add(func)

                for dep in depends:
                    getattr(self, dep)()

                self.logger.info(f"enabled {func.__name__}")
                return func(self, *args, **kwargs)

            return wrapper

        return decorator

    @feature()
    def dbus(self):
        self.bind_many(
            "/run/dbus",
            str(self.xdg_runtime_dir / "bus"),
            mode=BindMode.RW,
        )
        self.keepenv("DBUS_SESSION_BUS_ADDRESS")

    @feature(depends=("gpu",))
    def x11(self):
        self.bind_many(
            "/tmp/.X11-unix",
            "/tmp/.ICE-unix",
            str(self.home / ".Xauthority"),
            *glob(str(self.xdg_runtime_dir / "ICE*")),
            mode=BindMode.RW,
        )
        self.keepenv("DISPLAY", "XAUTHORITY")

    @feature(depends=("gpu",))
    def wayland(self):
        self.bind_many(
            *glob(str(self.xdg_runtime_dir / "wayland*")),
            mode=BindMode.RW,
        )
        self.setenv(
            QT_QPA_PLATFORM="wayland:xcb",
            MOZ_ENABLE_WAYLAND=1,
            GDK_BACKEND="wayland",
            _JAVA_AWT_WM_NONREPARENTING=1,
        )
        self.keepenv("WAYLAND_DISPLAY")

    @feature()
    def audio(self):
        self.bind_many(
            *glob(str(self.xdg_runtime_dir / "pulse*")),
            *glob(str(self.xdg_runtime_dir / "pipewire*")),
            {"src": "/dev/snd", "mode": BindMode.DEV},
            mode=BindMode.RW,
        )

    @feature()
    def gpu(self, shader_cache=True):
        self.bind_many(
            "/dev/dri",
            *glob("/dev/nvidia*"),
            mode=BindMode.DEV,
        )
        self.keepenv("__GL_THREADED_OPTIMIZATION")
        if shader_cache:
            self.bind_many(
                "$XDG_CACHE_HOME/mesa_shader_cache",
                "$XDG_CACHE_HOME/radv_builtin_shaders64",
                "$XDG_CACHE_HOME/nv",
                "$XDG_CACHE_HOME/nvidia",
            )

    @feature(depends=("gpu",))
    def nvidia(self):
        if not Path("/dev/nvidiactl").exists():
            raise RuntimeError("Nvidia GPU not present on host.")
        self.logger.info("prefer Nvidia GPU")

        self.setenv(
            __NV_PRIME_RENDER_OFFLOAD="1",
            __GLX_VENDOR_LIBRARY_NAME="nvidia",
            __VK_LAYER_NV_optimus="NVIDIA_only",
            VK_DRIVER_FILES="/usr/share/vulkan/icd.d/nvidia_icd.json",
        )

    @feature()
    def desktop(self):
        self.wayland()
        self.x11()
        self.audio()

    @feature(depends=("gpu", "wayland", "x11"))
    def mangohud(self):
        self.home_bind(".config/MangoHud")
        self.setenv(MANGOHUD=1)

    @feature()
    def locale(self, newlocale):
        self.logger.info(f"set new locale to {newlocale}")
        self.setenv(
            LANG=newlocale,
            LC_ALL=newlocale,
        )
        self.file(dedent(f"LANG={newlocale}\nLC_TIME={newlocale}"), "/etc/locale.conf")
