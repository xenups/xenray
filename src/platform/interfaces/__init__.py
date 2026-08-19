"""OS abstraction contracts.

Business logic (services, controllers) depends ONLY on these interfaces — never
directly on ctypes, winreg, subprocess commands, or registry keys. Each adapter
has a Windows implementation and (where sensible) Linux/macOS or no-op versions.

Factories in ``src.platform.factory`` return the right adapter for the running
OS, so callers stay fully platform-agnostic.
"""

from __future__ import annotations

import socket
from abc import ABC, abstractmethod
from typing import Any, List, Optional, Protocol, runtime_checkable


class INetworkAdapter(ABC):
    """Physical-NIC discovery: IP + DNS, no name blacklists or IP heuristics."""

    @abstractmethod
    def get_physical_nic_candidates(self) -> list[dict]:
        """Physical, up, gateway-bearing adapters: [{"name","ip","iftype",
        "operstatus","gateway"}]. Empty when none/unavailable."""

    @abstractmethod
    def get_physical_lan_ip(self) -> Optional[str]:
        """Primary physical LAN IPv4, or None if unavailable (never fabricated)."""

    @abstractmethod
    def get_system_dns_servers(self) -> list[str]:
        """System DNS servers (physical adapters only)."""

    @abstractmethod
    def get_primary_interface(self):
        """(name, ip, subnet, gateway) of the default-route interface."""

    @abstractmethod
    def ping_mtu(self, host: str, payload_size: int, timeout: int) -> bool:
        """Ping host with Don't Fragment (DF) flag set for the given payload size."""


class ITunDnsConfigurator(ABC):
    """Windows TUN DNS + NRPT: keeps all netsh/powershell behind this wall."""

    @abstractmethod
    def configure_tun_dns(self, config_file_path: str, adapter_name: str) -> bool:
        """Configure DNS + NRPT on the TUN adapter for a TUN profile."""

    @abstractmethod
    def cleanup_tun_dns(self, adapter_name: str) -> None:
        """Restore system DNS / remove NRPT rules (idempotent)."""


class IFirewallAdapter(ABC):
    """Host firewall rule management (LAN sharing allow rules)."""

    @abstractmethod
    def add_rule(self, name: str, port: int, interface: Optional[str] = None) -> bool:
        """Add an inbound allow rule for *port*."""

    @abstractmethod
    def remove_rule(self, name: str) -> bool:
        """Remove the rule named *name*."""

    @abstractmethod
    def check_lan_firewall_rule(self) -> bool:
        """Check if the LAN sharing inbound allow rule exists."""

    @abstractmethod
    def add_lan_firewall_rule(self, ports: List[int]) -> bool:
        """Create the LAN sharing inbound allow rule for the given ports."""

    @abstractmethod
    def remove_lan_firewall_rule(self) -> None:
        """Remove the LAN sharing inbound allow rule."""


class ISystemSettingsAdapter(ABC):
    """System-level settings (e.g. Windows SMHR registry toggle, Autostart)."""

    @abstractmethod
    def read_smhr_state(self) -> Optional[bool]:
        """Current SMHR enabled state, or None if unsupported."""

    @abstractmethod
    def set_smhr_state(self, enabled: bool) -> None:
        """Apply SMHR enabled state."""

    @abstractmethod
    def suppress_smhr(self) -> Optional[bool]:
        """Disable SMHR and return the prior state (for later restore)."""

    @abstractmethod
    def restore_smhr(self, previous: Optional[bool]) -> None:
        """Restore SMHR to *previous*."""

    @abstractmethod
    def is_autostart_enabled(self, app_name: str = "XenRay") -> bool:
        """Check if application autostart is enabled on logon."""

    @abstractmethod
    def enable_autostart(self, app_name: str, launch_command: str) -> tuple[bool, str]:
        """Enable application autostart on user logon."""

    @abstractmethod
    def disable_autostart(self, app_name: str = "XenRay") -> tuple[bool, str]:
        """Disable application autostart."""


from src.platform.interfaces.route import IRouteAdapter
from src.platform.interfaces.tun_driver import ITunDriverAdapter


@runtime_checkable
class IProcessAdapter(Protocol):
    """Process-creation flags, startupinfo, elevation, and restart per platform."""

    def get_subprocess_flags(self) -> int:  # pragma: no cover - protocol
        """subprocess creation flags for the platform."""

    def get_startupinfo(self) -> Optional[Any]:  # pragma: no cover - protocol
        """StartupInfo for the platform, or None."""

    def is_elevated(self) -> bool:  # pragma: no cover - protocol
        """Check if current process is running with administrative/root privileges."""

    def request_elevation(
        self, executable: Optional[str] = None, params: Optional[str] = None
    ) -> bool:  # pragma: no cover - protocol
        """Request UAC elevation or restart as admin."""

    def initialize_environment(self) -> None:  # pragma: no cover - protocol
        """Initialize OS environment flags (e.g. DPI awareness, AppUserModelID)."""

    def restart_as_admin(self) -> None:  # pragma: no cover - protocol
        """Restart application with elevated administrative privileges."""

    def supports_interactive_elevation(self) -> bool:  # pragma: no cover - protocol
        """Whether this platform supports interactive GUI/CLI UAC elevation."""

    def get_elevation_hint(self) -> str:  # pragma: no cover - protocol
        """Platform-specific message instructing the user how to elevate manually."""

    def acquire_singleton_mutex(self, name: str = "XenRay_Singleton_Mutex_v1") -> bool:  # pragma: no cover - protocol
        """Acquire single-instance mutex. Returns False if another instance is already running."""


# Re-export for convenience.
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
