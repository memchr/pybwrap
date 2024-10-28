#!/usr/bin/python
import logging

import platformdirs
from pybwrap import BindMode, BwrapSandbox, BwrapArgumentParser, handle_binds, HOME
import sys
import os
from pathlib import Path


DEFAULT_WINE_PREFIX = Path.home() / ".wine"
DEFAULT_PROTON_PREFIX = platformdirs.user_data_path("proton")
STEAM_PATH = platformdirs.user_data_path("Steam")
PROTON_PATH = STEAM_PATH / "steamapps/common/Proton - Experimental"


def main():
    logging.basicConfig(
        level=logging.ERROR,
        format="%(levelname)s:%(name)s: %(message)s",
    )
    logger = logging.getLogger("swine")

    parser = BwrapArgumentParser(
        description="Run wine in bubblewrap sandbox",
    )

    parser.add_flag_unshare_net()
    parser.add_flag_keep()
    parser.add_flag_keep_user()
    parser.add_flag_bind()
    parser.add_flag_etc()

    parser.add_flag_mangohud()
    parser.add_flag_nvidia()
    parser.feature_flags.add_argument(
        "-N",
        "--nvidia-fix",
        action="store_true",
        help="Nvidia workaround for Vulkan.",
    )

    parser.feature_flags.add_argument(
        "-p",
        "--proton",
        action="store_true",
        help="Use proton",
    )
    parser.feature_flags.add_argument(
        "-P",
        "--proton-fix",
        action="store_true",
        help="Proton workarounds for performance denigration.",
    )
    parser.add_argument(
        "-s",
        "--shell",
        action="store_true",
        help="Run shell command instead of wine.",
    )
    parser.mount_flags.add_argument(
        "-x",
        "--prefix",
        type=str,
        help="Use a wine prefix, the default is $_prefix.",
    )
    parser.add_args_command()
    args = parser.parse_args()

    if len(args.command) == 0:
        parser.error("a command is required")

    logger.setLevel(args.loglevel)

    if os.path.basename(__file__) == "proton":
        logger.debug("running as proton")
        args.proton = True

    # Do not change user name when running wine on default prefix
    if args.prefix is None and not args.proton:
        logger.debug("keep user name because default wine prefix is used")
        args.keep_user = True

    sandbox = BwrapSandbox(
        hostname=f"wine-{os.getpid()}",
        keep_child=args.keep,
        keep_user=args.keep_user,
        loglevel=args.loglevel,
    )
    sandbox.unshare(net=args.unshare_net)
    sandbox.keepenv(
        "DXVK_CONFIG_FILE",
        "DXVK_DEBUG",
        "DXVK_ENABLE_NVAPI",
        "DXVK_HUD",
        "DXVK_LOG_LEVEL",
        "DXVK_LOG_PATH",
        "DXVK_STATE",
        "DXVK_STATE_CACHE_PATH",
        "GAMEMODERUNEXEC",
        "MANGOHUD",
        "MANGOHUD_CONFIG",
        "PROTON_NO_ESYNC",
        "PROTON_NO_FSYNC",
        "PROTON_USE_WINED3D",
        "VKD3D_CONFIG",
        "VKD3D_FEATURE_LEVEL",
        "VK_DRIVER_FILES",
        "VK_INSTANCE_LAYERS",
        "WINEDLLOVERRIDES",
        "WINEFSYNC",
        "WINEDEBUG",
    )
    sandbox.bind_all(
        HOME / "downloads",
        HOME / "tmp",
        {"src": HOME / ".local/bin", "mode": BindMode.RO},
        mode=BindMode.RW,
    )
    sandbox.desktop()
    sandbox.mangohud(enable=args.mangohud)

    # bind exe path
    exe = Path(args.command[0])
    if not exe.suffix:
        exe = exe.with_suffix(".exe")
    logger.info(f"Windows exe is: {exe}")
    if exe.exists():
        sandbox.bind(exe.parent.absolute(), mode=BindMode.RW)

    # prefer nvidia
    if args.nvidia:
        sandbox.nvidia()
        if args.nvidia_fix:
            logger.info("Nvidia GPU workaround enabled")
            sandbox.setenv(__GLX_VENDOR_LIBRARY_NAME="bla")

    if args.proton_fix:
        logger.info("Proton workaround enabled")
        sandbox.setenv(
            VKD3D_CONFIG="dxr11",
            PROTON_CONFIG="dxr11",
            VKD3D_FEATURE_LEVEL="12_1",
            PROTON_HIDE_NVIDIA_GPU="0",
            PROTON_ENABLE_NVAPI="1",
        )

    if args.bind:
        handle_binds(args.bind, sandbox.bind)

    if args.proton:
        prefix = str(args.prefix or DEFAULT_PROTON_PREFIX)
        sandbox.setenv(
            STEAM_COMPAT_CLIENT_INSTALL_PATH=str(STEAM_PATH),
            STEAM_COMPAT_DATA_PATH=str(sandbox.resolve_path(prefix)),
        )
        sandbox.bind_all(
            str(PROTON_PATH),
            prefix,
            mode=BindMode.RW,
        )
        adverb = [str(PROTON_PATH / "proton"), "runinprefix"]
    else:
        prefix = str(args.prefix or DEFAULT_WINE_PREFIX)
        sandbox.setenv(WINEPREFIX=str(sandbox.resolve_path(prefix)))
        sandbox.bind(prefix, mode=BindMode.RW)
        adverb = ["wine"]

    if args.shell:
        adverb = []

    Path(prefix).mkdir(exist_ok=True)
    sandbox.dir(prefix)
    sandbox.exec(adverb + args.command)


if __name__ == "__main__":
    sys.exit(main())
