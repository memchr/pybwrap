#!/usr/bin/python

import logging
import os
from pathlib import Path
import sys
import shutil

import platformdirs

from pybwrap.bwrap import BindMode, Bwrap, BwrapSandbox
from pybwrap.cli import BwrapArgumentParser, handle_binds

PROFILE_STORAGE = Path.home() / "profiles"


logging.basicConfig(
    level=logging.ERROR,
    format="%(levelname)s:%(name)s: %(message)s",
)
logger = logging.getLogger("profile")

home = Path.home()


def main():
    shell = os.getenv("SHELL", "bash")
    parser = BwrapArgumentParser(
        description="Run wine in bubblewrap sandbox",
        add_help=True,
        default_cmd=[shell],
    )
    parser.add_flag_keep()
    parser.add_flag_cwd()
    g = parser.add_mutually_exclusive_group()
    g.add_argument("profile", type=str, nargs="?", help="Profile to launch")
    g.add_argument("-l", "--list", action="store_true", help="List all profiles")
    parser.add_args_command()
    parser.add_flag_bind()
    parser.add_flag_etc()
    parser.add_argument(
        "-C",
        "--create",
        action="store_true",
        help="Create the profile if it doesn't exist",
    )
    args = parser.parse_args()
    if args.list:
        logger.info("listing profiles")
        for d in PROFILE_STORAGE.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                print(str(d.name))
        return 0

    if not args.profile:
        parser.error("a profile name is required")

    profile = args.profile

    profile_path = PROFILE_STORAGE / profile

    if len(args.command) == 0:
        parser.error("a command is required")

    sandbox: BwrapSandbox = BwrapSandbox(
        clearenv=True,
        profile=str(profile_path),
        keep_child=args.keep,
        hostname=profile,
        loglevel=args.loglevel,
        path=(".bin",) + Bwrap.DEFAULT_PATH,
    )
    sandbox.resolve_path
    logger.setLevel(args.loglevel)

    if not profile_path.exists():
        if not args.create:
            parser.error(f"Profile {profile} does not exist!")
        logger.info(f"profile `{profile}` not found, creating...")
        profile_path.mkdir()
        # copy .config/fish and .config/
        config_home = platformdirs.user_config_path()
        copy(config_home / "fish", profile_path / ".config/fish")
        copy(config_home / "lf", profile_path / ".config/lf")
        copy(config_home / "bat", profile_path / ".config/bat")

    sandbox.unshare()
    sandbox.desktop()
    sandbox.bind_all(
        "downloads",
        "tmp",
        ".local/bin",
        {"src": ".local/bin", "mode": BindMode.RO},
        mode=BindMode.RW,
        src_anchor=home,
        dest_anchor=sandbox.home,
    )
    sandbox.dir(str(sandbox.home / ".bin"))
    if args.bind:
        handle_binds(args.bind, sandbox.bind)
    if args.cwd:
        sandbox.bind(os.getcwd(), mode=BindMode.RW)
        sandbox.chdir()
    sandbox.exec(args.command)


def copy(src, dest=None):
    dest = dest or src
    if not isinstance(src, Path):
        src = Path(src)
    if not isinstance(dest, Path):
        dest = Path(dest)
    if not src.exists():
        logger.warning(f"Source directory '{src}' does not exist.")
        return
    try:
        shutil.copytree(src, dest)
        logger.info(f"Directory '{src}' copied to '{dest}' successfully.")
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
