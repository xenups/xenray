"""Platform factory — returns the right adapter for the running OS.

Services depend on the interfaces only; this is the single place that decides
Windows vs POSIX wiring.
"""

from __future__ import annotations

from src.platform.interfaces import (
    IFirewallAdapter,
    INetworkAdapter,
    IRouteAdapter,
    ISystemSettingsAdapter,
    ITunDnsConfigurator,
    ITunDriverAdapter,
)


def _is_windows() -> bool:
    import os

    return os.name == "nt"


def _is_macos() -> bool:
    import sys

    return sys.platform == "darwin"


def get_network_adapter() -> INetworkAdapter:
    if _is_windows():
        from src.platform.windows.network import WindowsNetworkAdapter

        return WindowsNetworkAdapter()
    from src.platform.posix import PosixNetworkAdapter

    return PosixNetworkAdapter()


def get_tun_dns_configurator() -> ITunDnsConfigurator:
    if _is_windows():
        from src.platform.windows.tun_dns import WindowsTunDnsConfigurator

        return WindowsTunDnsConfigurator()
    from src.platform.posix import NoopTunDnsConfigurator

    return NoopTunDnsConfigurator()


def get_system_settings_adapter() -> ISystemSettingsAdapter:
    if _is_windows():
        from src.platform.windows.settings import WindowsSystemSettingsAdapter

        return WindowsSystemSettingsAdapter()
    from src.platform.posix import NoopSystemSettingsAdapter

    return NoopSystemSettingsAdapter()


def get_firewall_adapter() -> IFirewallAdapter:
    if _is_windows():
        from src.platform.windows.firewall import WindowsFirewallAdapter

        return WindowsFirewallAdapter()
    from src.platform.posix import NoopFirewallAdapter

    return NoopFirewallAdapter()


def get_process_adapter():
    if _is_windows():
        from src.platform.windows.process import WindowsProcessAdapter

        return WindowsProcessAdapter()
    from src.platform.posix import PosixProcessAdapter

    return PosixProcessAdapter()


def get_tun_driver_adapter() -> ITunDriverAdapter:
    if _is_windows():
        from src.platform.windows.tun_driver import WindowsTunDriverAdapter

        return WindowsTunDriverAdapter()
    from src.platform.posix.tun_driver import NoopTunDriverAdapter

    return NoopTunDriverAdapter()


def get_route_adapter() -> IRouteAdapter:
    if _is_windows():
        from src.platform.windows.route import WindowsRouteAdapter

        return WindowsRouteAdapter()
    elif _is_macos():
        from src.platform.macos.route import MacosRouteAdapter

        return MacosRouteAdapter()
    else:
        from src.platform.linux.route import LinuxRouteAdapter

        return LinuxRouteAdapter()


__all__ = [
    "get_network_adapter",
    "get_tun_dns_configurator",
    "get_system_settings_adapter",
    "get_firewall_adapter",
    "get_process_adapter",
    "get_tun_driver_adapter",
    "get_route_adapter",
]
