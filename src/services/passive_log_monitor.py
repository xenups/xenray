"""
Passive log monitor for extracting network error signals.

Monitors Xray/Singbox log files for error patterns without active probing.
"""

import threading
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from src.services.network_stability_observer import NetworkStabilityObserver


class PassiveLogMonitor:
    """
    Monitors log files for error patterns and feeds signals to observer.

    Zero overhead - only reads logs that are already being written.
    """

    def __init__(self, observer: NetworkStabilityObserver):
        """
        Initialize log monitor.

        Args:
            observer: NetworkStabilityObserver to receive signals
        """
        self._observer = observer
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._log_files: list[Path] = []
        self._file_positions: dict[Path, int] = {}

    def start_monitoring(self, log_files: list[str]):
        """
        Start monitoring log files.

        Args:
            log_files: List of log file paths to monitor
        """
        if self._monitoring:
            return

        self._log_files = [Path(f) for f in log_files if f]
        self._file_positions = {f: 0 for f in self._log_files}
        self._monitoring = True

        # Start background thread
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="LogMonitor"
        )
        self._monitor_thread.start()

        logger.info(f"[LogMonitor] Started monitoring {len(self._log_files)} log files")

    def stop_monitoring(self):
        """Stop monitoring log files."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
        logger.info("[LogMonitor] Stopped")

    def _monitor_loop(self):
        """Background monitoring loop (runs in separate thread)."""
        while self._monitoring:
            try:
                for log_file in self._log_files:
                    self._check_file(log_file)

                # Sleep briefly to avoid busy loop
                time.sleep(0.5)  # Check every 500ms
            except Exception as e:
                logger.error(f"[LogMonitor] Error in monitoring loop: {e}")

    def _check_file(self, log_file: Path):
        """
        Check a log file for new lines and parse them.

        Args:
            log_file: Path to log file
        """
        if not log_file.exists():
            return

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                # Seek to last known position
                current_pos = self._file_positions.get(log_file, 0)
                f.seek(current_pos)

                # Read new lines
                new_lines = f.readlines()

                # Update position
                self._file_positions[log_file] = f.tell()

                # Parse each line
                for line in new_lines:
                    self._parse_line(line.strip())

        except Exception as e:
            logger.debug(f"[LogMonitor] Error reading {log_file}: {e}")

    def _parse_line(self, line: str):
        """
        Parse a log line for error patterns.

        Args:
            line: Log line to parse
        """
        if not line:
            return

        # Feed to observer's pattern matcher
        self._observer.parse_log_line(line)
