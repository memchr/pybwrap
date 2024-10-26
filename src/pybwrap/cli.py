import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Callable

from . import BwrapSandbox, BindMode

BINDMODE_MAP = {
    "r": BindMode.RO,
    "w": BindMode.RW,
    "d": BindMode.DEV,
}

LOGLEVEL_MAP = {
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}

bind_spec = re.compile(r"^(?P<src>[^:]+)(?::(?P<dest>[^:]*))?(?::(?P<mode>[rwd]))?$")


def handle_binds(binds: list[str], callback: Callable):
    for bind in binds:
        m = bind_spec.match(bind)
        src = Path(m.group("src"))
        dest = Path(m.group("dest") or src)
        mode = BINDMODE_MAP[m.group("mode") or "r"]
        callback(src, dest, mode)


class BwrapArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, enable_all=False, default_cmd=None, **kwargs):
        super().__init__(*args, add_help=False, **kwargs)
        if enable_all:
            self.add_flag_keep()
            self.add_flag_dbus()
            self.add_flag_x11()
            self.add_flag_wayland()
            self.add_flag_gpu()
            self.add_flag_nvidia()
            self.add_flag_audio()
            self.add_flag_desktop()
            self.add_flag_cwd()
            self.add_flag_user()
            self.add_flag_hostname()
            self.add_flag_bind_mount()
            self.add_flag_keep_user()
            self.add_flag_keep_hostname()
            self.add_flag_unshare_net()
            self.add_flag_mangohud()
            self.add_flag_rootfs()
            self.add_flag_locale()
        self.add_argument(
            "--loglevel", type=str, default="error", help="Logging level."
        )

        self.add_argument(
            "--help", action="store_true", help="Show this help message and exit."
        )
        self.add_argument(
            "command",
            nargs=argparse.REMAINDER,
            help="Command to run with bwrap",
        )
        self.default_cmd = default_cmd

    class BwrapArgs:
        dbus: bool
        x11: bool
        wayland: bool
        nvidia: bool
        gpu: bool
        audio: bool
        cwd: bool
        unshare_net: bool
        desktop: bool
        mangohud: bool
        keep: bool
        user: str
        keep_user: bool
        keep_hostname: bool
        locale: str
        v: tuple[str]
        loglevel: int

    def parse_args(self, *args, **kwargs) -> tuple[BwrapArgs, list[str]]:
        args, unknown = super().parse_known_args(*args, **kwargs)

        if args.help:
            self.print_help()
            print("\nnotes:\n  Unrecognized arguments will be passed to bwrap")
            sys.exit(0)

        if len(args.command) == 0:
            if self.default_cmd:
                args.command = self.default_cmd
            else:
                self.print_help()
                print("\nError: Command required", file=sys.stderr)
                sys.exit(1)
        command = unknown + (
            args.command[1:] if args.command[0] == "--" else args.command
        )

        args.loglevel = LOGLEVEL_MAP.get(getattr(args, "loglevel"), logging.ERROR)

        return args, command

    def add_flag_keep(self):
        self.add_argument(
            "-k",
            "--keep",
            action="store_true",
            help="Do not kill sandbox's process when bwrap exits.",
        )

    def add_flag_dbus(self):
        self.add_argument("-d", "--dbus", action="store_true", help="Enable dbus.")

    def add_flag_x11(self):
        self.add_argument("-x", "--x11", action="store_true", help="Enable X11.")

    def add_flag_wayland(self):
        self.add_argument(
            "-w", "--wayland", action="store_true", help="Enable Wayland."
        )

    def add_flag_gpu(self):
        self.add_argument(
            "-g", "--gpu", action="store_true", help="Enable GPU access (dri)."
        )

    def add_flag_nvidia(self):
        self.add_argument(
            "-n", "--nvidia", action="store_true", help="Prefer NVIDIA graphics."
        )

    def add_flag_audio(self):
        self.add_argument("-a", "--audio", action="store_true", help="Enable sound.")

    def add_flag_desktop(self):
        self.add_argument(
            "-D",
            "--desktop",
            action="store_true",
            help="enable x11, wayland, GPU and sound",
        )

    def add_flag_cwd(self):
        self.add_argument(
            "-c", "--cwd", action="store_true", help="Bind current working directory."
        )

    def add_flag_user(self):
        self.add_argument(
            "-u",
            "--user",
            type=str,
            help="Change username to <username>.",
            default="user",
        )

    def add_flag_hostname(self):
        self.add_argument(
            "-h",
            "--hostname",
            type=str,
            help="Change hostname to <hostname>.",
            default=f"sandbox-{os.getpid()}",
        )

    def add_flag_bind_mount(self):
        self.add_argument(
            "-v",
            action="append",
            type=str,
            help="Bind mount",
        )

    def add_flag_keep_user(self):
        self.add_argument(
            "-U", "--keep-user", action="store_true", help="Use parent username."
        )

    def add_flag_keep_hostname(self):
        self.add_argument(
            "-H", "--keep-hostname", action="store_true", help="Use parent hostname."
        )

    def add_flag_rootfs(self):
        self.add_argument(
            "-r", "--rootfs", type=str, help="Use <rootfs> as / instead of parent's /."
        )

    def add_flag_locale(self):
        self.add_argument("-l", "--locale", type=str, help="Sandbox's locale.")

    def add_flag_unshare_net(self):
        self.add_argument(
            "-o",
            "--unshare-net",
            action="store_true",
            help="Create a new network namespace.",
        )

    def add_flag_mangohud(self):
        self.add_argument(
            "-m", "--mangohud", action="store_true", help="Enable mangohud."
        )


def main():
    logging.basicConfig(
        level=logging.ERROR,
        format="%(levelname)s:%(name)s: %(message)s",
    )

    parser = BwrapArgumentParser(
        description="Create new bubblewrap container",
        enable_all=True,
    )

    args, command = parser.parse_args()

    sandbox = BwrapSandbox(
        user=args.user,
        hostname=args.hostname,
        keep_user=args.keep_user,
        keep_hostname=args.keep_hostname,
        loglevel=args.loglevel,
        keep_child=args.keep,
    )
    sandbox.unshare(net=args.unshare_net)
    if args.dbus:
        sandbox.dbus()
    if args.x11:
        sandbox.x11()
    if args.wayland:
        sandbox.wayland()
    if args.audio:
        sandbox.audio()
    if args.gpu:
        sandbox.gpu()
    if args.nvidia:
        sandbox.nvidia()
    if args.cwd:
        sandbox.bind(os.getcwd(), mode=BindMode.RW)
        sandbox.chdir()
    if args.desktop:
        sandbox.desktop()
    if args.locale is not None:
        sandbox.locale(args.locale)
    if args.mangohud:
        sandbox.mangohud(enable=True)
    sandbox.home_bind_many("downloads", "tmp", mode=BindMode.RW)
    if args.v:
        handle_binds(args.v, sandbox.bind)
    sandbox.exec(command)
