"""System domain services (LAN sharing and Task Scheduler)."""

from __future__ import annotations

from src.services.system.lan_service import LanService
from src.services.system.task_scheduler import (
    is_supported,
    is_task_registered,
    register_task,
    unregister_task,
)

__all__ = [
    "LanService",
    "is_task_registered",
    "register_task",
    "unregister_task",
    "is_supported",
]
