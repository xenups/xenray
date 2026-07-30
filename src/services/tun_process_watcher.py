"""Subprocess Death Watcher for Sing-box & Xray TUN engines."""

import os
import threading
import time
from typing import Callable, Optional

from loguru import logger


class TUNProcessWatcher:
    """
    Asynchronous watcher monitoring subprocess life cycles (Sing-box / Xray).

    Fires `on_crash_callback` instantly if the process terminates unexpectedly
    (i.e. without an explicit `stop()` request).
    """

    POLL_INTERVAL = 0.5  # seconds

    def __init__(
        self,
        process,
        on_crash_callback: Callable[[int, str], None],
        log_file_path: Optional[str] = None,
        name: str = "TUNProcess",
    ):
        """
        Initialize process watcher.

        Args:
            process: Popen instance to monitor
            on_crash_callback: Callback invoked on unexpected process exit (returncode, log_snippet)
            log_file_path: Optional path to stdout/stderr log file for crash context
            name: Human-readable process name for logging
        """
        self._process = process
        self._on_crash = on_crash_callback
        self._log_file_path = log_file_path
        self._name = name

        self._intentional_stop = False
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start monitoring process lifecycle in background thread."""
        if self._running or not self._process:
            return

        self._running = True
        self._intentional_stop = False
        self._thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name=f"TUNProcessWatcher-{self._name}",
        )
        self._thread.start()
        logger.info(f"[TUNProcessWatcher] Started watching {self._name} (PID: {self._process.pid})")

    def stop(self):
        """Mark process termination as intentional to suppress crash events."""
        self._intentional_stop = True
        self._running = False
        logger.info(f"[TUNProcessWatcher] Stopped watching {self._name} (intentional shutdown)")

    def _watch_loop(self):
        """Main monitoring loop polling process status."""
        try:
            while self._running and self._process:
                exit_code = self._process.poll()
                if exit_code is not None:
                    # Process has terminated
                    self._running = False
                    if self._intentional_stop:
                        logger.debug(
                            f"[TUNProcessWatcher] {self._name} exited normally (code {exit_code}, intentional)"
                        )
                    else:
                        log_snippet = self._read_log_snippet()
                        logger.error(
                            f"[TUNProcessWatcher] {self._name} CRASHED / TERMINATED UNEXPECTEDLY "
                            f"(exit code {exit_code}). Log: {log_snippet}"
                        )
                        if self._on_crash:
                            try:
                                self._on_crash(exit_code, log_snippet)
                            except Exception as e:
                                logger.error(f"[TUNProcessWatcher] Error in crash callback: {e}")
                    break
                time.sleep(self.POLL_INTERVAL)
        except Exception as e:
            logger.error(f"[TUNProcessWatcher] Error in watch loop for {self._name}: {e}")

    def _read_log_snippet(self) -> str:
        """Read last lines of process log file for crash context."""
        if not self._log_file_path or not os.path.exists(self._log_file_path):
            return "No log file available"

        try:
            with open(self._log_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                snippet = "".join(lines[-10:]).strip()
                return snippet if snippet else "Log file empty"
        except Exception as e:
            return f"Failed to read log: {e}"
