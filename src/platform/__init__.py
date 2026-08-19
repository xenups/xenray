"""OS abstraction layer.

Structure:
    interfaces/   ABC/Protocol contracts (INetworkAdapter, ITunDnsConfigurator, ...)
    windows/      ctypes/iphlpapi/netsh/powershell implementations
    posix/        no-op / minimal stubs for Linux & macOS
    factory.py    returns the right adapter for the running OS
    constants.py  every OS string in one place
"""

from __future__ import annotations

from src.platform.factory import (
    get_network_adapter,
    get_process_adapter,
    get_system_settings_adapter,
    get_tun_dns_configurator,
)

__all__ = [
    "get_network_adapter",
    "get_process_adapter",
    "get_system_settings_adapter",
    "get_tun_dns_configurator",
]
