"""XrayProcessManager - OS-level process lifecycle for the Xray core.

Single responsibility: run the Xray binary, track its PID, monitor it, kill it
safely, and own the PID file. No config knowledge, no DNS/NRPT/SMHR logic — the
facade (``XrayService``) composes this with the Windows-network and SNI-helper
bits that sit above the raw process.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Optional

from src.core.constants import XRAY_EXECUTABLE, XRAY_PID_FILE
from src.core.logger import logger
from src.platform.constants import XRAY_KILL_GRACE_SECONDS
from src.utils.process_utils import ProcessUtils

# Graceful-kill wait before forcing (seconds).
KILL_GRACE_SECONDS = 1.0


class XrayProcessManager:
    """Owns the Xray subprocess: launch, PID, status, teardown."""

    def __init__(self):
        self._process = None
        self._pid: Optional[int] = None

    # -- launch ----------------------------------------------------------
    def start(self, config_file_path: str, log_file: str) -> Optional[int]:
        """Launch the Xray binary with the given config; write the PID file.

        Returns the new PID, or None on failure.
        """
        cmd = [XRAY_EXECUTABLE, "run", "-c", config_file_path]
        logger.debug(f"[XrayProcessManager] Executing command: {' '.join(cmd)}")
        logger.debug(f"[XrayProcessManager] Log file: {log_file}")
        try:
            self._process = ProcessUtils.run_command(cmd, stdout_file=log_file, stderr_file=log_file)
        except (OSError, Exception) as e:  # noqa: BLE001 - wrap subprocess errors
            logger.error(f"[XrayProcessManager] Failed to start Xray: {e}")
            self._process = None
            return None

        if not self._process:
            logger.error("[XrayProcessManager] Failed to start process")
            return None

        self._pid = self._process.pid
        logger.info(f"[XrayProcessManager] Started with PID {self._pid}")
        try:
            with open(XRAY_PID_FILE, "w") as f:
                f.write(str(self._pid))
        except Exception as e:  # noqa: BLE001
            logger.error(f"[XrayProcessManager] Failed to write PID file: {e}")
        return self._pid

    # -- status ----------------------------------------------------------
    @property
    def pid(self) -> Optional[int]:
        if self._pid and ProcessUtils.is_running(self._pid):
            return self._pid
        return None

    @property
    def is_running(self) -> bool:
        return self.pid is not None

    # -- PID-file adoption / cleanup ------------------------------------
    def adopt_pid_file(self) -> None:
        """Restore PID from file if it's still running (CLI state adoption)."""
        if os.path.exists(XRAY_PID_FILE):
            try:
                with open(XRAY_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    self._pid = old_pid
                    logger.debug(f"[XrayProcessManager] Restored PID {self._pid} from file")
            except Exception:  # noqa: BLE001
                pass

    def cleanup_previous_instance(self) -> None:
        """Kill any previous instance using PID file, then clear it."""
        if os.path.exists(XRAY_PID_FILE):
            try:
                with open(XRAY_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    logger.info(f"[XrayProcessManager] Found orphan process {old_pid}, killing...")
                    ProcessUtils.kill_process(old_pid, force=True)
                os.remove(XRAY_PID_FILE)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[XrayProcessManager] Failed to cleanup old PID file: {e}")

    # -- teardown --------------------------------------------------------
    @staticmethod
    def kill_all_core_instances() -> None:
        """Kill every running xray core binary and wait for handles to release.

        Used by the installer before replacing the binary (Windows: taskkill /F;
        Unix: pkill -9). Routes through the platform process layer so no raw
        kill command strings leak into business logic.
        """
        try:
            from src.platform.factory import get_process_adapter

            adapter = get_process_adapter()
            flags = adapter.get_subprocess_flags()
            startupinfo = adapter.get_startupinfo()

            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/IM", "xray.exe"],
                    capture_output=True,
                    timeout=5,
                    creationflags=flags,
                    startupinfo=startupinfo,
                )
            else:
                subprocess.run(
                    ["pkill", "-9", "xray"],
                    capture_output=True,
                    timeout=5,
                )
            # Give Windows time to release the file handle on the old binary.
            time.sleep(XRAY_KILL_GRACE_SECONDS)
        except Exception as e:  # noqa: BLE001 - best-effort kill
            logger.warning(f"[XrayInstaller] Failed to kill xray process: {e}")

    def kill_and_cleanup(self) -> Optional[int]:
        """Kill the process (memory PID then PID file) and remove the PID file.

        Returns the killed PID or None.
        """
        pid_to_kill = self._pid
        if not pid_to_kill and os.path.exists(XRAY_PID_FILE):
            try:
                with open(XRAY_PID_FILE, "r") as f:
                    pid_to_kill = int(f.read().strip())
            except Exception:  # noqa: BLE001
                pass

        if not pid_to_kill:
            return None

        try:
            logger.info(f"[XrayProcessManager] Stopping process {pid_to_kill}")
            ProcessUtils.kill_process(pid_to_kill, force=False)
            deadline = time.monotonic() + KILL_GRACE_SECONDS
            while ProcessUtils.is_running(pid_to_kill) and time.monotonic() < deadline:
                time.sleep(0.05)
            if ProcessUtils.is_running(pid_to_kill):
                logger.warning(f"[XrayProcessManager] Graceful stop timed out for PID {pid_to_kill}, forcing kill")
                ProcessUtils.kill_process(pid_to_kill, force=True)

            self._pid = None
            self._process = None

            if os.path.exists(XRAY_PID_FILE):
                try:
                    os.remove(XRAY_PID_FILE)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[XrayProcessManager] Failed to remove PID file: {e}")
            return pid_to_kill
        except Exception as e:  # noqa: BLE001
            logger.error(f"[XrayProcessManager] Failed to stop Xray: {e}")
            return None
