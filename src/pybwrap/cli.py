import argparse
import logging
import os
import re
import socket
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


def main():
    logging.basicConfig(
        level=logging.ERROR,
        format="%(levelname)s:%(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Create new bubblewrap container", add_help=False
    )

    # Define the flags
    parser.add_argument(
        "-k",
        "--keep",
        action="store_true",
        help="Do not kill sandbox's process when bwrap exits.",
    )
    parser.add_argument("-d", "--dbus", action="store_true", help="Enable dbus.")
    parser.add_argument("-x", "--x11", action="store_true", help="Enable X11.")
    parser.add_argument("-w", "--wayland", action="store_true", help="Enable Wayland.")
    parser.add_argument(
        "-g", "--gpu", action="store_true", help="Enable GPU access (dri)."
    )
    parser.add_argument(
        "-n", "--nvidia", action="store_true", help="Prefer NVIDIA graphics."
    )
    parser.add_argument("-a", "--audio", action="store_true", help="Enable sound.")
    parser.add_argument(
        "-D", "--desktop", action="store_true", help="enable x11,wayland,GPU and sound"
    )
    parser.add_argument(
        "-p", "--pwd", action="store_true", help="Bind current working directory."
    )
    parser.add_argument(
        "-u",
        "--user",
        type=str,
        help="Change username to <username>.",
        default="user",
    )
    parser.add_argument(
        "-h",
        "--hostname",
        type=str,
        help="Change hostname to <hostname>.",
        default=f"sandbox-{os.getpid()}",
    )
    parser.add_argument(
        "-v",
        action="append",
        type=str,
        help="Bind mount",
    )
    parser.add_argument(
        "-U", "--keep-user", action="store_true", help="Use parent username."
    )
    parser.add_argument(
        "-H", "--keep-hostname", action="store_true", help="Use parent hostname."
    )
    parser.add_argument(
        "-r", "--rootfs", type=str, help="Use <rootfs> as / instead of parent's /."
    )
    parser.add_argument("-l", "--locale", type=str, help="Sandbox's locale.")
    parser.add_argument("--loglevel", type=str, default="error", help="Logging level.")
    # Add help option manually
    parser.add_argument(
        "--help", action="store_true", help="Show this help message and exit."
    )
    # Capture any additional unrecognized flags
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run with bwrap",
    )
    # Parse the arguments
    args, unknown = parser.parse_known_args()

    if args.help:
        parser.print_help()
        print("\nnotes:\n  Unrecognized arguments will be passed to bwrap")
        return 1

    if len(args.command) == 0:
        parser.print_help()
        print("\nError: Command required", file=sys.stderr)
        return 1

    command = unknown + (args.command[1:] if args.command[0] == "--" else args.command)
    loglevel = LOGLEVEL_MAP.get(args.loglevel, logging.ERROR)
    user = os.getlogin() if args.keep_user else args.user
    hostname = socket.gethostname() if args.keep_hostname else args.hostname
    sandbox = BwrapSandbox(
        user=user,
        hostname=hostname,
        home=Path("/home") / user,
        loglevel=loglevel,
        keep_child=args.keep,
    )
    sandbox.unshare()
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
    if args.pwd:
        sandbox.home_bind(os.getcwd(), BindMode.RW)
    if args.desktop:
        sandbox.desktop()
    if args.locale is not None:
        sandbox.locale(args.locale)
    sandbox.home_bind_many("downloads", "tmp", mode=BindMode.RW)
    if args.v:
        handle_binds(args.v, sandbox.bind)
    sandbox.exec(command)
