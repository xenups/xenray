"""Windows ISystemSettingsAdapter — SMHR (Smart Multi-Homed Name Resolution).

The old PlatformUtils.read_smhr_state / set_smhr_state / suppress_smhr /
restore_smhr registry logic lives here.  Callers use
``src.platform.factory.get_system_settings_adapter()``.
"""

from __future__ import annotations

from typing import Optional

from src.platform.interfaces import ISystemSettingsAdapter

# Windows SMHR registry key — single source of truth.
_SMHR_REGISTRY_KEY = r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters"


def _read_smhr_state() -> Optional[bool]:
    """Read the current SMHR enabled state from the Windows registry.

    Returns:
        True  — SMHR is enabled (OS default)
        False — SMHR is disabled
        None  — state could not be read (non-Windows or registry error)
    """
    try:
        import winreg  # Windows-only

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SMHR_REGISTRY_KEY) as key:
            try:
                value, _ = winreg.QueryValueEx(key, "DisableSmartNameResolution")
                return value == 0  # 0 = SMHR on, 1 = SMHR off
            except FileNotFoundError:
                return True  # Key absent → SMHR is enabled (OS default)
    except Exception:
        return None


def _set_smhr_state(enabled: bool) -> None:
    """Enable or disable SMHR via the Windows registry.

    Args:
        enabled: True to enable SMHR (OS default), False to disable.
    """
    try:
        import winreg  # Windows-only

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SMHR_REGISTRY_KEY, access=winreg.KEY_SET_VALUE) as key:
            # DisableSmartNameResolution: 0 = on, 1 = off
            winreg.SetValueEx(
                key,
                "DisableSmartNameResolution",
                0,
                winreg.REG_DWORD,
                0 if enabled else 1,
            )
            # Also toggle the parallel A+AAAA sub-feature
            winreg.SetValueEx(
                key,
                "DisableParallelAandAAAA",
                0,
                winreg.REG_DWORD,
                0 if enabled else 1,
            )
    except Exception as exc:
        from src.core.logger import logger  # lazy to avoid circular import at module level

        logger.warning(f"[WindowsSystemSettingsAdapter] Could not set SMHR registry value: {exc}")


def _suppress_smhr() -> Optional[bool]:
    """Disable SMHR for a TUN session and return the previous state.

    Only takes effect on Windows; returns None immediately on other platforms.

    Returns:
        The SMHR state *before* suppression (True = was enabled, False = was
        already disabled, None = not Windows / registry error).  Pass this
        value to :func:`restore_smhr` on teardown.
    """
    import os

    if os.name != "nt":
        return None

    from src.core.logger import logger  # lazy to avoid circular import

    previous = _read_smhr_state()
    if previous is True:
        logger.info("[WindowsSystemSettingsAdapter] Disabling SMHR to prevent DNS leaks during TUN session")
        _set_smhr_state(enabled=False)
    return previous


def _restore_smhr(previous_state: Optional[bool]) -> None:
    """Restore SMHR to its pre-TUN state.

    Args:
        previous_state: The value returned by :func:`suppress_smhr`.
            If True, SMHR is re-enabled.  Any other value is a no-op.
    """
    import os

    if os.name != "nt":
        return
    if previous_state is True:
        from src.core.logger import logger  # lazy to avoid circular import

        logger.info("[WindowsSystemSettingsAdapter] Restoring SMHR to enabled state")
        _set_smhr_state(enabled=True)


_RUN_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_TASK_NAME = "XenRayStartup"


def _is_autostart_enabled(app_name: str = "XenRay") -> bool:
    # 1. Check Task Scheduler
    try:
        import subprocess

        cmd = f"Get-ScheduledTask -TaskName '{_TASK_NAME}' -ErrorAction SilentlyContinue"
        result = subprocess.run(
            ["powershell", "-Command", cmd],
            capture_output=True,
            text=True,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass

    # 2. Check Registry
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_REGISTRY_PATH, 0, winreg.KEY_READ) as key:
            try:
                val, _ = winreg.QueryValueEx(key, app_name)
                return bool(val)
            except FileNotFoundError:
                return False
    except Exception:
        return False


def _enable_autostart(app_name: str, launch_command: str) -> tuple[bool, str]:
    import os
    import subprocess
    import sys
    from pathlib import Path

    # If running as Admin, prefer Task Scheduler
    try:
        import ctypes

        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        is_admin = False

    if is_admin:
        try:
            if getattr(sys, "frozen", False):
                cwd = str(Path(sys.executable).parent)
                exe = sys.executable
                argument_param = ""
            else:
                cwd = str(Path(__file__).parent.parent.parent.parent)
                exe = sys.executable
                main_script = str(Path(__file__).parent.parent.parent / "main.py")
                argument_param = f"-Argument '\"{main_script}\"'"

            username = os.environ.get("USERNAME", "")
            userdomain = os.environ.get("USERDOMAIN", "")
            user_id = f"{userdomain}\\{username}" if userdomain and username else username

            ps_script = f"""
            $Action = New-ScheduledTaskAction -Execute '{exe}' {argument_param} -WorkingDirectory '{cwd}'
            $Trigger = New-ScheduledTaskTrigger -AtLogOn
            $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -StartWhenAvailable -ExecutionTimeLimit 0
            $Principal = New-ScheduledTaskPrincipal -UserId '{user_id}' -RunLevel Highest `
                -LogonType Interactive
            Register-ScheduledTask -TaskName '{_TASK_NAME}' -Action $Action -Trigger $Trigger `
                -Principal $Principal -Settings $Settings -Force
            """
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                creationflags=0x08000000,
            )
            if result.returncode == 0:
                return True, "Startup enabled via Task Scheduler"
        except Exception:
            pass

    # Fallback to Registry
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, launch_command)
        return True, "Startup enabled via Registry"
    except Exception as e:
        return False, str(e)


def _disable_autostart(app_name: str = "XenRay") -> tuple[bool, str]:
    # 1. Unregister Task Scheduler
    try:
        import subprocess

        ps_command = f"Unregister-ScheduledTask -TaskName '{_TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue"
        subprocess.run(
            ["powershell", "-Command", ps_command],
            capture_output=True,
            text=True,
            creationflags=0x08000000,
        )
    except Exception:
        pass

    # 2. Unregister Registry
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        return True, "Startup disabled"
    except Exception as e:
        return False, str(e)


class WindowsSystemSettingsAdapter(ISystemSettingsAdapter):
    """SMHR & Autostart — Windows registry & Task Scheduler toggle."""

    def read_smhr_state(self) -> Optional[bool]:
        return _read_smhr_state()

    def set_smhr_state(self, enabled: bool) -> None:
        return _set_smhr_state(enabled)

    def suppress_smhr(self) -> Optional[bool]:
        return _suppress_smhr()

    def restore_smhr(self, previous: Optional[bool]) -> None:
        return _restore_smhr(previous)

    def is_autostart_enabled(self, app_name: str = "XenRay") -> bool:
        return _is_autostart_enabled(app_name)

    def enable_autostart(self, app_name: str, launch_command: str) -> tuple[bool, str]:
        return _enable_autostart(app_name, launch_command)

    def disable_autostart(self, app_name: str = "XenRay") -> tuple[bool, str]:
        return _disable_autostart(app_name)


__all__ = ["WindowsSystemSettingsAdapter"]
