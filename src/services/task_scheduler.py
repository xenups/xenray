"""
Windows Task Scheduler integration for XenRay.

Registers the application to run on user logon using PowerShell.
Prioritizes Task Scheduler (supports Admin privileges) over Registry.
"""

import subprocess
import sys
import os
from pathlib import Path

from loguru import logger

from src.utils.platform_utils import PlatformUtils
from src.utils.process_utils import ProcessUtils

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


def _get_launch_details() -> tuple[str, str, str]:
    """
    Get launch details for the current execution mode.

    Returns:
        Tuple of (executable_path, arguments, single_string_command)
    """
    if PlatformUtils.is_frozen():
        exe = sys.executable
        return exe, "", f'"{exe}"'
    else:
        python_exe = sys.executable
        main_script = str(Path(__file__).parent.parent / "main.py")
        return python_exe, f'"{main_script}"', f'"{python_exe}" "{main_script}"'


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
    """Enable startup via Windows Registry (standard privileges)."""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_SET_VALUE
        )
        _, _, launch_command = _get_launch_details()
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

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_SET_VALUE
        )
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
        # Check if task exists using powershell
        cmd = f"Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue"
        result = subprocess.run(
            ["powershell", "-Command", cmd],
            capture_output=True,
            text=True,
            startupinfo=_get_startupinfo(),
        )
        return result.returncode == 0
    except Exception:
        return False


def _enable_via_task_scheduler() -> tuple[bool, str]:
    """
    Enable startup via Windows Task Scheduler.
    Requires Admin privileges for 'Highest' run level.
    """
    try:
        exe, args, _ = _get_launch_details()

        # Determine working directory
        if getattr(sys, "frozen", False):
            # In frozen mode, sys.executable is the exe
            cwd = str(Path(sys.executable).parent)
        else:
            # In script mode, we want the project root
            cwd = str(Path(__file__).parent.parent.parent)

        # Get current user in DOMAIN\User format from environment
        username = os.environ.get("USERNAME", "")
        userdomain = os.environ.get("USERDOMAIN", "")
        user_id = f"{userdomain}\\{username}" if userdomain and username else username

        # Handle empty arguments for frozen builds
        argument_param = f"-Argument '{args}'" if args else ""

        # Construct PowerShell command
        # UserId is required for Interactive LogonType
        ps_script = f"""
        $Action = New-ScheduledTaskAction -Execute '{exe}' {argument_param} -WorkingDirectory '{cwd}'
        $Trigger = New-ScheduledTaskTrigger -AtLogOn
        $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit 0
        $Principal = New-ScheduledTaskPrincipal -UserId '{user_id}' -RunLevel Highest -LogonType Interactive
        Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force
        """

        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            startupinfo=_get_startupinfo(),
        )

        if result.returncode == 0:
            logger.info(f"[TaskScheduler] Enabled startup via Task Scheduler (CWD: {cwd}, User: {user_id})")
            return True, "Startup enabled via Task Scheduler"
        else:
            logger.error(f"[TaskScheduler] Task Scheduler failed: {result.stderr}")
            return False, f"Task Scheduler failed: {result.stderr}"

    except Exception as e:
        logger.error(f"[TaskScheduler] Failed to enable via Task Scheduler: {e}")
        return False, str(e)


def is_task_registered() -> bool:
    """Check if startup is enabled (Task Scheduler OR Registry)."""
    if PlatformUtils.get_platform() != "windows":
        return False

    return _is_task_scheduler_enabled() or _is_registry_enabled()


def register_task() -> tuple[bool, str]:
    """
    Enable startup.
    Tries Task Scheduler if Admin (for elevation support),
    otherwise falls back to Registry.

    Returns:
        Tuple of (success, message)
    """
    if PlatformUtils.get_platform() != "windows":
        return False, "Only supported on Windows"

    # If running as Admin, prefer Task Scheduler to support elevated startup
    if ProcessUtils.is_admin():
        success, msg = _enable_via_task_scheduler()
        if success:
            return True, msg
        logger.warning(
            "[TaskScheduler] Admin Task Scheduler failed, falling back to Registry"
        )

    # Fallback to Registry (or default for non-admin)
    return _enable_via_registry()


def unregister_task() -> tuple[bool, str]:
    """
    Disable startup - removes from both Task Scheduler and Registry.

    Returns:
        Tuple of (success, message)
    """
    if PlatformUtils.get_platform() != "windows":
        return False, "Only supported on Windows"

    # Always try to remove both to be clean
    reg_success, reg_msg = _disable_via_registry()

    task_success = False
    try:
        ps_command = f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue"
        result = subprocess.run(
            ["powershell", "-Command", ps_command],
            capture_output=True,
            text=True,
            startupinfo=_get_startupinfo(),
        )
        task_success = result.returncode == 0
    except Exception:
        pass

    if reg_success or task_success:
        return True, "Startup disabled"
    
    return False, "Failed to disable startup"


def is_supported() -> bool:
    """Check if startup management is supported on this platform."""
    return PlatformUtils.get_platform() == "windows"
