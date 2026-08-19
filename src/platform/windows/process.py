"""Windows Process Adapter — manages Windows-specific process flags, elevation, DPI, and restart."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from typing import Optional

import psutil
from loguru import logger

from src.platform.interfaces import IProcessAdapter


class WindowsProcessAdapter(IProcessAdapter):
    """Windows subprocess creation flags, hidden-window STARTUPINFO, and UAC elevation."""

    def get_subprocess_flags(self) -> int:
        """CREATE_NO_WINDOW (0x08000000) on Windows, 0 elsewhere."""
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    def get_startupinfo(self) -> Optional[subprocess.STARTUPINFO]:
        """STARTUPINFO hiding the console window, or None if unavailable."""
        STARTUPINFO = getattr(subprocess, "STARTUPINFO", None)
        if STARTUPINFO:
            startupinfo = STARTUPINFO()
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
            startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            return startupinfo
        return None

    def is_elevated(self) -> bool:
        """Return True if current process is running with Administrator privileges."""
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    @staticmethod
    def _current_executable() -> str:
        """Return the real application executable path.

        Under a PyInstaller one-file build, the running process is the memory
        bootstrap (temp ``_MEI...`` extraction), but ``sys.executable`` still
        points at the real frozen ``.exe`` on disk. Prefer that; fall back to
        ``sys.argv[0]`` when it is a concrete ``.exe`` so we never hand UAC a
        temp extraction folder as the executable.
        """
        try:
            if getattr(sys, "frozen", False) and sys.executable:
                if sys.executable.lower().endswith(".exe"):
                    return sys.executable
            if sys.argv and sys.argv[0].lower().endswith(".exe"):
                return os.path.abspath(sys.argv[0])
        except Exception:
            pass
        return sys.executable

    def request_elevation(self, executable: Optional[str] = None, params: Optional[str] = None) -> bool:
        """Request UAC elevation or restart executable as administrator."""
        try:
            import ctypes
            import subprocess

            if not executable:
                executable = self._current_executable()
            if params is None:
                params = subprocess.list2cmdline(sys.argv[1:]) if len(sys.argv) > 1 else ""

            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
            return ret > 32
        except Exception:
            return False

    def supports_interactive_elevation(self) -> bool:
        """Windows supports interactive UAC prompt elevation."""
        return True

    def get_elevation_hint(self) -> str:
        """Instruction hint for running with elevated permissions on Windows."""
        return "💡 Please run from an Administrator PowerShell/CMD"

    def initialize_environment(self) -> None:
        """Set Windows DPI awareness and explicit AppUserModelID."""
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

        try:
            app_id = "xenups.xenray.gui.v2"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass

    def restart_as_admin(self) -> None:
        """Restart application as administrator on Windows."""
        try:
            executable = self._current_executable()
            params = self._restart_params()
            logger.info(f"[WindowsProcessAdapter] Restarting as admin: {executable} {params}")

            # STEP 1: Kill all child processes FIRST (to release file locks)
            current_pid = os.getpid()
            try:
                parent = psutil.Process(current_pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.kill()
                    except (psutil.NoSuchProcess, Exception):
                        pass
                time.sleep(0.3)
            except Exception as e:
                logger.warning(f"Error cleaning up child processes: {e}")

            # STEP 2: Launch new admin instance via elevation
            if self.request_elevation(executable=executable, params=params):
                logger.info("Process elevated successfully. Terminating current process...")
                # Give the spawned (elevated) process a moment to begin before we
                # tear the old one down, so the relaunch is never removed from the
                # job too early. Then os._exit: a bare sys.exit inside a GUI event
                # handler / worker thread only raises SystemExit, which can be
                # swallowed by the thread and Flet's async loop, leaving the
                # window alive and the old EXE locked.
                time.sleep(1.0)
                os._exit(0)
            else:
                logger.warning("Elevation request cancelled or failed")

        except Exception as e:
            logger.error(f"Failed to restart as admin: {e}")

    @staticmethod
    def _restart_params() -> str:
        """Command-line args to pass to the elevated relaunch.

        Under a frozen one-file EXE the program needs no extra args; under a
        source/dev run we must re-invoke the entry script (sys.argv[0]) so the
        relaunched interpreter actually starts the app.
        """
        try:
            import shlex

            frozen = getattr(sys, "frozen", False)
            args = list(sys.argv[1:])
            if not frozen and args and args[0].lower().endswith((".py", ".pyz")):
                # entry script already leading; keep as-is
                pass
            elif not frozen and sys.argv:
                # prepend the script so `python.exe <script> ...` relaunches the app
                args.insert(0, sys.argv[0])
            return " ".join(shlex.quote(a) for a in args)
        except Exception:
            return " ".join(sys.argv[1:])

    def acquire_singleton_mutex(self, name: str = "XenRay_Singleton_Mutex_v1") -> bool:
        """Acquire Windows single-instance mutex. Returns False if already running."""
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            mutex_name = f"Global\\{name}"
            ctypes.set_last_error(0)
            handle = kernel32.CreateMutexW(None, False, mutex_name)
            last_error = ctypes.get_last_error()
            logger.debug(f"[WindowsProcessAdapter] Mutex handle={handle}, last_error={last_error}")
            if last_error == 183:  # ERROR_ALREADY_EXISTS
                return False
            self._singleton_mutex = handle
            return True
        except Exception as e:
            logger.debug(f"[WindowsProcessAdapter] Mutex error: {e}")
            return True


__all__ = ["WindowsProcessAdapter"]
