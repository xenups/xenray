"""POSIX TUN driver adapter (no-op: TUN interfaces are kernel/utun natively)."""

from __future__ import annotations

from typing import Callable, Optional

from src.platform.interfaces.tun_driver import ITunDriverAdapter


class NoopTunDriverAdapter(ITunDriverAdapter):
    """No-op TUN driver adapter for POSIX platforms (Linux / macOS)."""

    def is_driver_available(self) -> bool:
        """POSIX kernels provide native tun/utun interfaces."""
        return True

    def ensure_driver(
        self,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """No external driver binary needed on POSIX."""
        return True


__all__ = ["NoopTunDriverAdapter"]
