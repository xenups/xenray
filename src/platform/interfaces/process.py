"""Process management, elevation, and execution abstraction contract."""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


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
