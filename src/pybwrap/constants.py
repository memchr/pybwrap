import os
from pathlib import Path


def _xdg_path(var_name: str, fallback: Path) -> Path:
    return Path(os.getenv(var_name, fallback)).expanduser().resolve()


HOME = Path.home()
XDG_RUNTIME_DIR = _xdg_path("XDG_RUNTIME_DIR", "/run/user/" + str(os.getuid()))
XDG_CONFIG_HOME = _xdg_path("XDG_CONFIG_HOME", HOME / ".config")
XDG_CACHE_HOME = _xdg_path("XDG_CACHE_HOME", HOME / ".cache")
XDG_DATA_HOME = _xdg_path("XDG_DATA_HOME", HOME / ".local" / "share")
XDG_STATE_HOME = _xdg_path("XDG_STATE_HOME", HOME / ".local" / "state")

SHELL = os.getenv("SHELL", "/usr/bin/bash")

F_ETC_PASSWD = f"""\
root:x:0:0::/root:/usr/bin/bash
bin:x:1:1::/:/usr/bin/nologin
daemon:x:2:2::/:/usr/bin/nologin
nobody:x:65534:65534:Kernel Overflow User:/:/usr/bin/nologin
{{user}}:x:{{uid}}:{{gid}}::{{home}}:{SHELL}
"""

F_ETC_GROUP = """
root:x:0:root
bin:x:1:daemon
nobody:x:65534:
daemon:x:2:bin
{user}:x:{gid}:
"""

F_ETC_NSSWITCH = """
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
"""

F_ETC_HOSTNAME = """
127.0.0.1       localhost       localhost.localdomain
::1             localhost       localhost.localdomain
127.0.0.1       {hostname}      {hostname}.localdomain
::1             {hostname}      {hostname}.localdomain
127.0.0.1       {hostname}.local
"""

ETC_WHITELIST = (
    "/etc/alsa",
    "/etc/avahi",
    "/etc/bash.bash_logout",
    "/etc/bash.bashrc",
    "/etc/bash_completion.d",
    "/etc/bindresvport.blacklist",
    "/etc/binfmt.d",
    "/etc/ca-certificates",
    "/etc/dbeaver",
    "/etc/dconf",
    "/etc/debuginfod",
    "/etc/default",
    "/etc/environment",
    "/etc/ethertypes",
    "/etc/fakechroot",
    "/etc/fish",
    "/etc/fonts",
    "/etc/fuse.conf",
    "/etc/gai.conf",
    "/etc/gdb",
    "/etc/geoclue",
    "/etc/gimp",
    "/etc/gnutls",
    "/etc/gprofng.rc",
    "/etc/gtk-2.0",
    "/etc/gtk-3.0",
    "/etc/host.conf",
    "/etc/ImageMagick-7",
    "/etc/imv_config",
    "/etc/inputrc",
    "/etc/issue",
    "/etc/java21-openjdk",
    "/etc/java11-openjdk",
    "/etc/java-openjdk",
    "/etc/jupyter",
    "/etc/krb5.conf",
    "/etc/ld.so.cache",
    "/etc/ld.so.conf",
    "/etc/ld.so.conf.d",
    "/etc/libao.conf",
    "/etc/libblockdev",
    "/etc/libinput",
    "/etc/libnl",
    "/etc/libreoffice",
    "/etc/locale.conf",
    "/etc/localtime",
    "/etc/login.defs",
    "/etc/lsb-release",
    "/etc/luarocks",
    "/etc/machine-id",
    "/etc/mailcap",
    "/etc/mercurial",
    "/etc/mime.types",
    "/etc/mono",
    "/etc/netconfig",
    "/etc/ODBCDataSources",
    "/etc/odbc.ini",
    "/etc/odbcinst.ini",
    "/etc/OpenCL",
    "/etc/openldap",
    "/etc/openmpi",
    "/etc/openpmix",
    "/etc/os-release",
    "/etc/papersize",
    "/etc/paperspecs",
    "/etc/pipewire",
    "/etc/pkcs11",
    "/etc/profile",
    "/etc/profile.d",
    "/etc/protocols",
    "/etc/prrte",
    "/etc/pulse",
    "/etc/R",
    "/etc/resolv.conf",
    "/etc/rhashrc",
    "/etc/rpc",
    "/etc/rsyncd.conf",
    "/etc/sasl2",
    "/etc/securetty",
    "/etc/services",
    "/etc/shells",
    "/etc/skel",
    "/etc/slsh.rc",
    "/etc/ssh",
    "/etc/ssl",
    "/etc/sway",
    "/etc/timidity",
    "/etc/trusted-key.key",
    "/etc/ts.conf",
    "/etc/ucx",
    "/etc/valkey",
    "/etc/vconsole.conf",
    "/etc/vde2",
    "/etc/vdpau_wrapper.cfg",
    "/etc/vulkan",
    "/etc/wgetrc",
    "/etc/webapps",
    "/etc/whois.conf",
    "/etc/X11",
    "/etc/xattr.conf",
    "/etc/xdg",
    "/etc/xml",
    "/etc/zsh",
)
