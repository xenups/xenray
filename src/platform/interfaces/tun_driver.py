"""TUN driver/environment abstraction interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional


class ITunDriverAdapter(ABC):
    """Abstraction for OS TUN driver installation, verification and bootstrapping."""

    @abstractmethod
    def ensure_driver(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Ensure platform TUN driver/environment is installed and ready."""
        pass

    @abstractmethod
    def is_driver_available(self) -> bool:
        """Check if TUN driver/module is present on the host."""
        pass
