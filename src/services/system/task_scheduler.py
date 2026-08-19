"""Startup management integration for XenRay.

Delegates startup registration, elevation handling, and registry/task-scheduler
operations to the Platform Layer (ISystemSettingsAdapter).
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.platform.factory import get_process_adapter, get_system_settings_adapter
from src.utils.platform_utils import PlatformUtils

APP_NAME = "XenRay"


def _get_launch_details() -> tuple[str, str, str]:
    """Get launch details for the current execution mode.

    Returns:
        Tuple of (executable_path, arguments, single_string_command)
    """
    if PlatformUtils.is_frozen():
        exe = sys.executable
        return exe, "", f'"{exe}"'
    else:
        python_exe = sys.executable
        main_script = str(Path(__file__).parent.parent.parent / "main.py")
        return python_exe, f'"{main_script}"', f'"{python_exe}" "{main_script}"'


def is_task_registered() -> bool:
    """Check if startup is enabled."""
    return get_system_settings_adapter().is_autostart_enabled(APP_NAME)


def register_task() -> tuple[bool, str]:
    """Enable startup via the system settings adapter."""
    _, _, launch_command = _get_launch_details()
    return get_system_settings_adapter().enable_autostart(APP_NAME, launch_command)


def unregister_task() -> tuple[bool, str]:
    """Disable startup via the system settings adapter."""
    return get_system_settings_adapter().disable_autostart(APP_NAME)


def is_supported() -> bool:
    """Check if startup management is supported on this platform."""
    return (
        get_process_adapter().get_subprocess_flags() != 0 or get_system_settings_adapter().read_smhr_state() is not None
    )


__all__ = [
    "APP_NAME",
    "is_task_registered",
    "register_task",
    "unregister_task",
    "is_supported",
]
