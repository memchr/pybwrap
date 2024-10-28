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
