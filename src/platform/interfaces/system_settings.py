"""System settings and OS configuration abstraction contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


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
