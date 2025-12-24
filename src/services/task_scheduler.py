"""
Windows Task Scheduler integration for XenRay.

Registers the application to run on user logon using PowerShell.
Falls back to Registry-based startup if Task Scheduler fails (no admin).
"""

import subprocess
import sys
from pathlib import Path

from loguru import logger

from src.utils.platform_utils import PlatformUtils

TASK_NAME = "XenRayStartup"
REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "XenRay"


def _get_startupinfo():
    """Get STARTUPINFO to hide console window on Windows."""
    if PlatformUtils.get_platform() == "windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        return startupinfo
    return None


def _get_launch_command() -> str:
    """Get the correct launch command for the current execution mode."""
    if PlatformUtils.is_frozen():
        return f'"{sys.executable}"'
    else:
        python_exe = sys.executable
        main_script = str(Path(__file__).parent.parent / "main.py")
        return f'"{python_exe}" "{main_script}"'


def _is_registry_enabled() -> bool:
    """Check if startup is enabled via Registry."""
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return bool(value)
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False


def _enable_via_registry() -> tuple[bool, str]:
    """Enable startup via Windows Registry (no admin required)."""
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_SET_VALUE)
        launch_command = _get_launch_command()
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command)
        winreg.CloseKey(key)
        logger.info(f"[TaskScheduler] Enabled startup via Registry: {launch_command}")
        return True, "Startup enabled via Registry"
    except Exception as e:
        logger.error(f"[TaskScheduler] Failed to enable via Registry: {e}")
        return False, str(e)


def _disable_via_registry() -> tuple[bool, str]:
    """Disable startup via Windows Registry."""
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass  # Already gone
        winreg.CloseKey(key)
        logger.info("[TaskScheduler] Disabled startup via Registry")
        return True, "Startup disabled"
    except Exception as e:
        logger.error(f"[TaskScheduler] Failed to disable via Registry: {e}")
        return False, str(e)


def _is_task_scheduler_enabled() -> bool:
    """Check if scheduled task is registered."""
    try:
        cmd = f"Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty TaskName"
        result = subprocess.run(
            ["powershell", "-Command", cmd],
            capture_output=True,
            text=True,
            startupinfo=_get_startupinfo(),
        )
        return TASK_NAME.lower() in result.stdout.lower()
    except Exception:
        return False


def is_task_registered() -> bool:
    """Check if startup is enabled (Task Scheduler OR Registry)."""
    if PlatformUtils.get_platform() != "windows":
        return False

    # Check both methods
    return _is_task_scheduler_enabled() or _is_registry_enabled()


def register_task() -> tuple[bool, str]:
    """
    Enable startup - uses Registry (doesn't require admin).

    Returns:
        Tuple of (success, message)
    """
    if PlatformUtils.get_platform() != "windows":
        return False, "Only supported on Windows"

    # Use Registry approach (no admin needed)
    return _enable_via_registry()


def unregister_task() -> tuple[bool, str]:
    """
    Disable startup - removes from both Task Scheduler and Registry.

    Returns:
        Tuple of (success, message)
    """
    if PlatformUtils.get_platform() != "windows":
        return False, "Only supported on Windows"

    # Remove from Registry
    success, msg = _disable_via_registry()

    # Also try to remove any existing Task Scheduler task (silently)
    try:
        ps_command = f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue"
        subprocess.run(
            ["powershell", "-Command", ps_command],
            capture_output=True,
            text=True,
            startupinfo=_get_startupinfo(),
        )
    except Exception:
        pass  # Ignore Task Scheduler errors

    return success, msg


def is_supported() -> bool:
    """Check if startup management is supported on this platform."""
    return PlatformUtils.get_platform() == "windows"
