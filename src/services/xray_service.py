"""Xray service for managing Xray process."""
import os
import subprocess
import time
from typing import Optional

from src.core.constants import XRAY_EXECUTABLE, XRAY_LOG_FILE, XRAY_PID_FILE
from src.core.logger import logger
from src.utils.process_utils import ProcessUtils

# Constants
PROCESS_START_DELAY = 0.2  # seconds - delay to ensure previous instance is terminated
STOP_CHECK_RETRIES = 3
STOP_CHECK_DELAY = 0.1  # seconds


class XrayService:
    """Service for managing Xray process."""

    def __init__(self):
        """Initialize Xray service."""
        self._process = None
        self._pid: Optional[int] = None
        self._cleanup_previous_instance()

    def _cleanup_previous_instance(self):
        """Check for and kill any previous instance using PID file."""
        if os.path.exists(XRAY_PID_FILE):
            try:
                with open(XRAY_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())

                if ProcessUtils.is_running(old_pid):
                    logger.info(
                        f"[XrayService] Found orphan process {old_pid}, killing..."
                    )
                    ProcessUtils.kill_process(old_pid, force=True)

                os.remove(XRAY_PID_FILE)
            except Exception as e:
                logger.warning(f"[XrayService] Failed to cleanup old PID file: {e}")

    def start(self, config_file_path: str) -> Optional[int]:
        """
        Start Xray with the given configuration.
        """
        # Ensure cleanup again just in case
        self._cleanup_previous_instance()

        logger.debug(f"[XrayService] Starting Xray with config: {config_file_path}")

        if not os.path.isfile(config_file_path):
            logger.error(f"[XrayService] Config not found: {config_file_path}")
            return None

        # Small delay to ensure previous instance is fully terminated
        time.sleep(PROCESS_START_DELAY)

        cmd = [XRAY_EXECUTABLE, "run", "-c", config_file_path]

        logger.debug(f"[XrayService] Executing command: {' '.join(cmd)}")
        logger.debug(f"[XrayService] Log file: {XRAY_LOG_FILE}")

        try:
            self._process = ProcessUtils.run_command(
                cmd, stdout_file=XRAY_LOG_FILE, stderr_file=XRAY_LOG_FILE
            )

            if self._process:
                self._pid = self._process.pid
                logger.info(f"[XrayService] Started with PID {self._pid}")

                # Write PID file
                try:
                    with open(XRAY_PID_FILE, "w") as f:
                        f.write(str(self._pid))
                except Exception as e:
                    logger.error(f"[XrayService] Failed to write PID file: {e}")

                return self._pid
            else:
                logger.error("[XrayService] Failed to start process")
                return None
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"[XrayService] Failed to start Xray: {e}")
            return None

    def stop(self) -> bool:
        """
        Stop Xray process.
        """
        # Checks memory PID first
        pid_to_kill = self._pid

        # If no memory PID, check file
        if not pid_to_kill and os.path.exists(XRAY_PID_FILE):
            try:
                with open(XRAY_PID_FILE, "r") as f:
                    pid_to_kill = int(f.read().strip())
            except:
                pass

        if not pid_to_kill:
            return True

        success = ProcessUtils.kill_process(pid_to_kill, force=False)

        if not success:
            # Try force kill
            success = ProcessUtils.kill_process(pid_to_kill, force=True)

        if success:
            # Wait briefly for process to terminate (non-blocking)
            for _ in range(STOP_CHECK_RETRIES):
                if not ProcessUtils.is_running(pid_to_kill):
                    break
                time.sleep(STOP_CHECK_DELAY)

            logger.info("[XrayService] Stopped")
            self._pid = None
            self._process = None

            # Remove PID file
            if os.path.exists(XRAY_PID_FILE):
                try:
                    os.remove(XRAY_PID_FILE)
                except:
                    pass

        return success

    def is_running(self) -> bool:
        """Check if Xray is running."""
        if self._pid and ProcessUtils.is_running(self._pid):
            return True

        # Check PID file fallback
        if os.path.exists(XRAY_PID_FILE):
            try:
                with open(XRAY_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    self._pid = old_pid  # Restore memory PID
                    return True
            except:
                pass

        return False

    @property
    def pid(self) -> Optional[int]:
        """Get Xray process ID."""
        return self._pid
