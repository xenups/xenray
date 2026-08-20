"""OS abstraction contracts.

Business logic (services, controllers) depends ONLY on these interfaces — never
directly on ctypes, winreg, subprocess commands, or registry keys. Each adapter
has a Windows implementation and (where sensible) Linux/macOS or no-op versions.

Factories in ``src.platform.factory`` return the right adapter for the running
OS, so callers stay fully platform-agnostic.
"""

from __future__ import annotations

import socket

from src.platform.interfaces.firewall import IFirewallAdapter
from src.platform.interfaces.network import INetworkAdapter
from src.platform.interfaces.process import IProcessAdapter
from src.platform.interfaces.route import IRouteAdapter
from src.platform.interfaces.system_settings import ISystemSettingsAdapter
from src.platform.interfaces.tun_dns import ITunDnsConfigurator
from src.platform.interfaces.tun_driver import ITunDriverAdapter

__all__ = [
    "INetworkAdapter",
    "ITunDnsConfigurator",
    "IFirewallAdapter",
    "ISystemSettingsAdapter",
    "IProcessAdapter",
    "ITunDriverAdapter",
    "IRouteAdapter",
    "socket",
]
