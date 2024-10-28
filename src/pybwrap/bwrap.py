from enum import Enum
from glob import glob
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable, Self, TypedDict, Unpack
import functools
import logging
import os
import socket

from pybwrap._secomp import SECCOMP_BLOCK_TIOCSTI
from pybwrap.constants import (
    F_ETC_GROUP,
    F_ETC_HOSTNAME,
    F_ETC_NSSWITCH,
    F_ETC_PASSWD,
    HOME,
    XDG_CACHE_HOME,
)
from pybwrap.path import _PathLike, ensure_path


class BindMode(Enum):
    RW = "rw"
    RO = "ro"
    DEV = "dev"


class BindOpts(TypedDict):
    mode: BindMode
    asis: bool
    dest_anchor: _PathLike | None = (None,)
    src_anchor: _PathLike | None = (None,)


class BindSpec(BindOpts):
    src: _PathLike
    dest: _PathLike | None


class Bwrap:
    DEFAULT_ETC_BINDS = (
        "bash.bashrc", "bash_completion.d", "binfmt.d", "bluetooth",
        "ca-certificates", "conf.d", "dconf", "default", "environment",
        "ethertypes", "fonts", "fuse.conf", "gai.conf", "grc.conf", "grc.fish",
        "grc.zsh",  "gtk-2.0", "gtk-3.0", "host.conf", "inputrc", "issue",
        "java-openjdk", "ld.so.cache", "ld.so.conf", "ld.so.conf.d",
        "libao.conf", "libinput", "libnl", "libpaper.d", "libva.conf",
        "locale.conf", "localtime", "login.defs", "lsb-release", "man_db.conf",
        "mime.types", "mono", "mtab", "named.conf", "machine-id", "ndctl",
        "ndctl.conf.d", "odbc.ini", "odbcinst.ini", "openldap", "openmpi",
        "openpmix", "os-release", "pam.d", "papersize", "paru.conf", "pipewire",
        "pkcs11", "povray", "profile", "profile.d", "protocols", "pulse",
        "rc_keymaps", "rc_maps.cfg", "request-key.conf", "request-key.d",
        "resolv.conf", "sane.d", "sasl2", "securetty", "security", "sensors.d",
        "sensors3.conf", "services", "shells", "ssl", "timidity", "tmpfiles.d",
        "tpm2-tss", "trusted-key.key", "ts.conf", "vdpau_wrapper.cfg", "vulkan",
        "wgetrc", "whois.conf", "wpa_supplicant", "xattr.conf", "xdg",
        "xinetd.d", "xml", "libreoffice", "java21-openjdk", "java11-openjdk"
    )  # fmt: skip
    DEFAULT_PATH = (
        ".local/bin",
        "go/bin",
        "/usr/local/bin",
        "/usr/local/sbin",
        "/usr/bin",
        "/usr/sbin",
        "/bin",
        "/sbin",
    )

    class Options(TypedDict):
        user: str
        hostname: str
        keep_user: bool
        keep_hostname: bool
        profile: str | None
        etc_binds: tuple[str]
        clearenv: bool
        path: tuple[str]
        keep_child: bool
        rootfs: Path | None
        loglevel: int

    DEFAULT_OPTIONS: Options = {
        "user": "user",
        "hostname": f"sandbox-{os.getpid()}",
        "keep_user": False,
        "keep_hostname": False,
        "profile": None,
        "etc_binds": DEFAULT_ETC_BINDS,
        "clearenv": True,
        "path": DEFAULT_PATH,
        "keep_child": False,
        "rootfs": None,
        "loglevel": logging.DEBUG,
    }

    def __init__(self, **kwargs: Unpack[Options]):
        opts = self.DEFAULT_OPTIONS | kwargs
        self.logger = logging.getLogger("bwrap")
        self.logger.setLevel(kwargs.get("loglevel", logging.ERROR))

        self.etc_binds = opts["etc_binds"]
        self.user = opts["user"]
        self.hostname = opts["hostname"]
        if opts["keep_user"]:
            self.user = os.getlogin()
        if opts["keep_hostname"]:
            self.hostname = socket.gethostname()

        self.home = Path("/home") / self.user
        self.logger.info(f"container HOME: {self.home}")

        # Adjusts the host's current working directory (CWD) for the container.
        self.host_cwd = Path.cwd()
        self.cwd = self.resolve_path(self.host_cwd)
        self.logger.info(f"container CWD: {self.cwd}")

        profile = opts["profile"]
        self.profile: Path | None = Path(profile) if profile else None

        self._init_container(opts)
        self._init_home(opts)
        self._init_environment_variables(opts)
        self._init_system_id(opts)

    def _init_container(self, opts: Options):
        """Base system"""
        rootfs = opts["rootfs"]
        self.args: list[str] = [
            "--tmpfs", "/tmp",
            "--proc", "/proc",
            "--dev", "/dev",
            "--dir", "/etc",
            "--dir", "/var",
            "--dir", "/run",
            "--unsetenv", "TMUX",
            "--seccomp", str(self.getfd(SECCOMP_BLOCK_TIOCSTI)),
        ]  # fmt: skip

        if rootfs is None:
            self.logger.info("Using host rootfs")
            self.bind_all(
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

        if not opts["keep_child"]:
            self.logger.info("Container will be killed when bwrap terminates")
            self.args.append("--die-with-parent")

    def _init_home(self, opts: Options):
        self.xdg_runtime_dir = Path(f"/run/user/{os.getuid()}")
        self.xdg_config_home = self.home / ".config"
        self.xdg_cache_home = self.home / ".cache"
        self.xdg_data_home = self.home / ".local" / "share"
        self.xdg_state_home = self.home / ".local" / "state"

        if self.profile:
            self.logger.info(f"using host {self.profile} as container home directory")
            self.args.extend(("--bind", str(self.profile), str(self.home)))

        self.dir(
            self.home,
            self.xdg_runtime_dir,
            self.xdg_cache_home,
            self.xdg_config_home,
            self.xdg_data_home,
            self.xdg_state_home,
            self.home / ".local" / "bin",
        )

        self.bind_all(
            HOME / ".config/user-dirs.dirs",
            HOME / ".config/user-dirs.locale",
        )

    def _init_environment_variables(self, opts: Options):
        if opts["clearenv"]:
            self.logger.info("Environment variables cleared")
            self.clearenv()

        path = (
            p if Path(p).is_absolute() else str(self.home / p)
            for p in opts["path"] or self.DEFAULT_PATH
        )

        self.setenv(
            HOME=self.home,
            SANDBOX=1,
            PATH=str.join(":", path),
            LOGNAME=self.user,
            USER=self.user,
            HOSTNAME=self.hostname,
            XDG_RUNTIME_DIR=self.xdg_runtime_dir,
            XDG_CONFIG_HOME=self.xdg_config_home,
            XDG_CACHE_HOME=self.xdg_cache_home,
            XDG_DATA_HOME=self.xdg_data_home,
            XDG_STATE_HOME=self.xdg_state_home,
            GTK_A11Y="none",
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

    def _init_system_id(self, opts: Options):
        """Initialize system identity, such as hostname and user name"""
        if not opts["keep_hostname"]:
            self.logger.info(f"Hostname changed to {self.hostname}")
            self.args.extend([
                "--unshare-uts",
                "--hostname", self.hostname
            ])  # fmt: skip

        self.logger.info(f"User name changed to {self.user}")
        uid, gid = os.getuid(), os.getgid()

        self.file(F_ETC_NSSWITCH, "/etc/nsswitch.conf")
        self.file(
            F_ETC_PASSWD.format(user=self.user, uid=uid, gid=gid, home=self.home),
            "/etc/passwd",
        )
        self.file(F_ETC_GROUP.format(user=self.user, gid=gid), "/etc/group")
        self.file(F_ETC_HOSTNAME.format(hostname=self.hostname), "/etc/hosts")
        self.file(f"{self.hostname}\n", "/etc/hostname")
        self.file(f"{self.user}:100000:65536\n", "/etc/subuid")
        self.file(f"{self.user}:100000:65536\n", "/etc/subgid")

    @staticmethod
    def format_bind_args(src: _PathLike, dest: _PathLike, mode):
        """Format bind arguments based on binding mode"""
        return {
            BindMode.RW: ("--bind-try", str(src), str(dest)),
            BindMode.RO: ("--ro-bind-try", str(src), str(dest)),
            BindMode.DEV: ("--dev-bind-try", str(src), str(dest)),
        }[mode]

    def resolve_path(
        self,
        path: _PathLike | None,
        translate=True,
        anchor=None,
    ) -> Path | None:
        """Resolve path and translate to absolute container path

        paths are translated as follows

        | host path             | container path       |
        | --------------------- | -------------------- |
        | /home/host/path       | /home/container/path |
        | /anywhere/else        | as is                |

        Args:
            path (Path): Path to translate
            translate (bool, optional): translate to container path. Defaults to True
            anchor(Path, optional): If specified, resolve relative paths against the anchor instead of the current working directory.
        Returns:
            Path: resolved path
        """
        if path is None:
            return None

        path = ensure_path(path)
        if not path.is_absolute():
            path = (anchor or self.host_cwd) / path

        try:
            return self.home / path.relative_to(HOME) if translate else path
        except ValueError:
            return path

    BIND_OPTIONS = {
        "mode": BindMode.RO,
        "asis": False,
        "src_anchor": None,
        "dest_anchor": None,
    }

    def bind(
        self,
        src: _PathLike,
        dest: _PathLike | None = None,
        **kwargs: Unpack[BindOpts],
    ) -> None:
        """Bind path mount from host to container

        Relative dest is treated as Path.cwd() / dest.

        To prevent host path translation, set asis to True.

        Args:
            src (_PathLike): path on the host, must be absolute path.
            dest (_PathLike | None, optional): default to src translated to container path.
            mode (BindMode, optional):Bind mode, one of RW, RO or DEV (allow device file access). Defaults to read only
            asis (bool, optional): if True, do not translate host path to container path. Defaults to False
            dest_anchor (Path): against where relative dest resolves
            src_anchor (Path): against where relative dest resolves
        """
        opts: BindOpts = self.BIND_OPTIONS | kwargs
        src, dest = ensure_path(src, dest or src)

        # resolve relative path
        src = self.resolve_path(
            src,
            translate=False,
            anchor=opts["src_anchor"],
        )
        dest = self.resolve_path(
            dest,
            translate=not opts["asis"],
            anchor=opts["dest_anchor"],
        )

        self.args.extend(self.format_bind_args(str(src), str(dest), opts["mode"]))

    def bind_all(
        self,
        *binds: _PathLike | BindSpec,
        **kwargs: Unpack[BindOpts],
    ):
        """Bind mutiple path to container

        Each binding can be specified as a path or a dictionary that will be used as kwargs for bind

        Args:
            *specs (BindSpec)
            mode (BindMode, optional): default `mode` for each bind
            asis (bool, optional): default `asis` for each bind
            dest_anchor (Path): against where relative dest resolves
            src_anchor (Path): against where relative dest resolves
        """
        opts = self.BIND_OPTIONS | kwargs

        for bind in binds:
            if isinstance(bind, dict):
                self.bind(**(opts | bind))
            else:
                self.bind(bind, **opts)

    def symlink(self, *symlink_spec: tuple[_PathLike]):
        for src, dest in symlink_spec:
            src, dest = self.resolve_path(src), self.resolve_path(dest)
            self.args.extend(["--symlink", str(src), str(dest)])

    def dir(self, *dirs: _PathLike):
        for dir in dirs:
            self.args.extend(("--dir", str(self.resolve_path(dir))))

    def tmpfs(self, *paths: _PathLike):
        for fs in paths:
            self.args.extend(("--tmpfs", str(self.resolve_path(fs))))

    @staticmethod
    def getfd(content: str | bytes) -> int:
        """Get file descriptor of content"""
        r, w = os.pipe()
        os.set_inheritable(r, True)
        if isinstance(content, str):
            content = content.encode()
        os.write(w, content)
        return r

    def file(self, content: str | bytes, dest: _PathLike, perms=None):
        """Copy from file descriptor to dest

        Default permission is 0666
        """
        if perms:
            self.args.extend(("--perms", str(perms)))

        self.args.extend(
            ("--file", str(self.getfd(content)), str(self.resolve_path(dest)))
        )

    def setenv(self, **kwargs: Any):
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

    def chdir(self, dest: _PathLike | None = None):
        """Change directory to dest, or to CWD if no dest was given"""
        if dest is None:
            dest = self.cwd
        self.args.extend(("--chdir", str(dest)))

    def exec(self, command: list[str]):
        """Start bwrap container with commands"""

        # fix paths in command
        host_home = str(HOME)
        for i, v in enumerate(command):
            if v[0] == "/" and host_home in v:
                command[i] = str(self.resolve_path(v))

        self._debug_print_args(command)

        # launch the container
        os.execvp(
            "bwrap",
            ["bwrap", "--args", str(self.getfd("\0".join(self.args)))] + command,
        )

    def _debug_print_args(self, command):
        if self.logger.level <= logging.DEBUG:
            args = self.args
            indices = [i for i, x in enumerate(args) if x.startswith("--")]
            for a in (
                " ".join(args[i:j]) for i, j in zip(indices, indices[1:] + [len(args)])
            ):
                self.logger.debug(f"arg: {a}")
            self.logger.debug(f"arg: {command}")


class BwrapSandbox(Bwrap):
    def __init__(self, *args, **kwargs: Unpack[Bwrap.Options]):
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
        self.bind_all(
            "/run/dbus",
            self.xdg_runtime_dir / "bus",
            mode=BindMode.RW,
        )
        self.keepenv("DBUS_SESSION_BUS_ADDRESS")

    @feature(depends=("gpu",))
    def x11(self):
        self.bind_all(
            "/tmp/.X11-unix",
            "/tmp/.ICE-unix",
            self.home / ".Xauthority",
            *glob(str(self.xdg_runtime_dir / "ICE*")),
            mode=BindMode.RW,
        )
        self.keepenv("DISPLAY", "XAUTHORITY")

    @feature(depends=("gpu",))
    def wayland(self):
        self.bind_all(
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
        self.bind_all(
            *glob(str(self.xdg_runtime_dir / "pulse*")),
            *glob(str(self.xdg_runtime_dir / "pipewire*")),
            {"src": "/dev/snd", "mode": BindMode.DEV},
            mode=BindMode.RW,
        )

    @feature()
    def gpu(self, shader_cache=True):
        self.bind_all(
            "/dev/dri",
            *glob("/dev/nvidia*"),
            mode=BindMode.DEV,
        )
        self.keepenv("__GL_THREADED_OPTIMIZATION")
        if shader_cache:
            self.bind_all(
                XDG_CACHE_HOME / "mesa_shader_cache",
                XDG_CACHE_HOME / "radv_builtin_shaders64",
                XDG_CACHE_HOME / "nv",
                XDG_CACHE_HOME / "nvidia",
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
    def mangohud(self, enable=True):
        self.bind(HOME / ".config/MangoHud")
        if enable:
            self.setenv(MANGOHUD=1)

    @feature()
    def locale(self, newlocale):
        self.logger.info(f"set new locale to {newlocale}")
        self.setenv(
            LANG=newlocale,
            LC_ALL=newlocale,
        )
        self.file(dedent(f"LANG={newlocale}\nLC_TIME={newlocale}"), "/etc/locale.conf")
