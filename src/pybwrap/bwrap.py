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
    XDG_RUNTIME_DIR,
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
        "etc_binds": None,
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
            "--seccomp", str(self.openfd(SECCOMP_BLOCK_TIOCSTI)),
        ]  # fmt: skip

        if rootfs is None:
            self.logger.info("Using host rootfs")
            binds = (
                "/usr",
                "/opt",
                "/sys/block",
                "/sys/bus",
                "/sys/class",
                "/sys/dev",
                "/sys/devices",
                "/sys/module",
                "/var/empty",
                "/var/cache/man",
                "/var/lib/alsa",
                "/run/systemd/resolve",
            ) + (self.etc_binds or ("/etc",))
            for v in binds:
                self.args.extend(("--ro-bind-try", v, v))
            self.bind("/dev/fuse", mode=BindMode.DEV)

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

        cp = self.bind_data
        cp(F_ETC_NSSWITCH, "/etc/nsswitch.conf")
        passwd_f = F_ETC_PASSWD.format(user=self.user, uid=uid, gid=gid, home=self.home)
        group_f = F_ETC_GROUP.format(user=self.user, gid=gid)
        subuid_f = f"{self.user}:100000:65536\n"
        cp(passwd_f, "/etc/passwd")
        cp(passwd_f, "/etc/passwd.OLD")
        cp(passwd_f, "/etc/passwd-")
        cp(group_f, "/etc/group")
        cp(group_f, "/etc/group-")
        cp(F_ETC_HOSTNAME.format(hostname=self.hostname), "/etc/hosts")
        cp(f"{self.hostname}\n", "/etc/hostname")
        cp(subuid_f, "/etc/subuid")
        cp(subuid_f, "/etc/subuid-")
        cp(subuid_f, "/etc/subgid")
        cp(subuid_f, "/etc/subgid-")
        cp(b"", "/etc/fstab")

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
    def openfd(content: str | bytes) -> int:
        """Get file descriptor of content"""
        r, w = os.pipe()
        os.set_inheritable(r, True)
        if isinstance(content, str):
            content = content.encode()
        os.write(w, content)
        return r

    class _FileArgs(TypedDict):
        perms: str | None
        anchor: _PathLike | None
        asis: bool

    def openfd_at(self, content: str | bytes, dest, **kwargs: Unpack[_FileArgs]) -> int:
        dest = self.resolve_path(
            dest,
            anchor=kwargs.get("anchor"),
            translate=not kwargs.get("asis", False),
        )
        perms = kwargs.get("perms")
        if perms:
            self.args.extend(("--perms", str(perms)))
        fd = self.openfd(content)

        return fd, dest

    def file(
        self,
        content: str | bytes,
        dest: _PathLike,
        **opts: Unpack[_FileArgs],
    ):
        """Copy from file descriptor to path in container

        Args:
            content (str | bytes): File content
            dest (_PathLike): File location
            perms (_type_, optional): Permission. Defaults to 0666
        """
        fd, dest = self.openfd_at(content, dest, **opts)
        self.args.extend(("--file", str(fd), str(dest)))

    def bind_data(
        self,
        content: str | bytes,
        dest: _PathLike,
        mode=BindMode.RO,
        **opts: Unpack[_FileArgs],
    ):
        """Bind data from file descriptor to path in container"""
        fd, dest = self.openfd_at(content, dest, **opts)

        if mode == BindMode.RO:
            self.args.extend(("--ro-bind-data", str(fd), str(dest)))
        elif mode == BindMode.RW:
            self.args.extend(("--bind-data", str(fd), str(dest)))

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
            ["bwrap", "--args", str(self.openfd("\0".join(self.args)))] + command,
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
            XDG_RUNTIME_DIR / "bus",
            mode=BindMode.RW,
        )
        self.keepenv("DBUS_SESSION_BUS_ADDRESS")

    @feature(depends=("gpu",))
    def x11(self):
        self.bind_all(
            "/tmp/.X11-unix",
            "/tmp/.ICE-unix",
            self.home / ".Xauthority",
            *glob(str(XDG_RUNTIME_DIR / "ICE*")),
            mode=BindMode.RW,
        )
        self.keepenv("DISPLAY", "XAUTHORITY")

    @feature(depends=("gpu",))
    def wayland(self):
        self.bind_all(
            *glob(str(XDG_RUNTIME_DIR / "wayland*")),
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
            *glob(str(XDG_RUNTIME_DIR / "pulse*")),
            *glob(str(XDG_RUNTIME_DIR / "pipewire*")),
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
                mode=BindMode.RW,
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
        self.bind_data(
            dedent(f"LANG={newlocale}\nLC_TIME={newlocale}"), "/etc/locale.conf"
        )
