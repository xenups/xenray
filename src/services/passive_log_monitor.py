"""
Passive Log Monitor Service.

Monitors Xray logs for connection failures and triggers callbacks.
"""

import os
import threading
import time
from typing import Callable, Optional

from loguru import logger

from src.core.constants import XRAY_LOG_FILE


class PassiveLogMonitor:
    """
    Monitors Xray log file for determining connection health.
    
    Features:
    - Tails the log file (handling rotation/recreation)
    - Detects specific error keywords
    - Debounces alerts to prevent flooding
    - Runs callbacks in separate threads to avoid blocking
    """

    # Error keywords that indicate connection failure (lowercase)
    ERROR_KEYWORDS = [
        # MUX and transport errors
        "failed to handler mux client connection",
        "transport closed",
        "generic::error",
        # Connection errors
        "connection reset by peer",
        "connection refused",
        "connection timed out",
        # Timeout errors
        "read timeout",
        "i/o timeout",
        "dial tcp",  # catches "dial tcp ... timeout" and "dial tcp ... refused"
        # Handshake and TLS errors
        "handshake failed",
        "tls handshake",
        # Retry and failure errors
        "all retry attempts failed",
        "failed to get",  # catches "failed to GET ..."
        "failed to post",
        # Network errors
        "no such host",
        "no route to host",
        "network is unreachable",
        "wsarecv:",  # Windows socket errors
    ]

    # Configuration
    CHECK_INTERVAL = 1.0  # seconds between log checks
    DEBOUNCE_SECONDS = 5.0  # Minimum time between alerts
    MAX_COOLDOWN_SECONDS = 300.0  # 5 minutes max
    BASE_COOLDOWN_SECONDS = 5.0

    def __init__(self, on_failure_callback: Callable[[], None] = None, log_file_path: str = None):
        """
        Initialize the monitor.

        Args:
            on_failure_callback: Function to call when connection failure is detected.
            log_file_path: Optional path to log file. Defaults to XRAY_LOG_FILE.
        """
        self._on_failure = on_failure_callback
        self._log_file_path = log_file_path or XRAY_LOG_FILE
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        # State
        self._last_alert_time = 0.0
        self._paused = False
        self._paused_until = 0.0
        self._consecutive_failures = 0

    def start(self):
        """Start the monitoring thread."""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            self._consecutive_failures = 0
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="PassiveLogMonitor"
            )
            self._thread.start()
            logger.info(f"[PassiveLogMonitor] Started monitoring: {self._log_file_path}")

    def stop(self):
        """Stop the monitoring thread."""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
            self._stop_event.set()
            
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            
            self._thread = None
            logger.info("[PassiveLogMonitor] Stopped monitoring")

    def pause(self, duration: float = 0):
        """
        Pause monitoring.
        
        Args:
            duration: If > 0, pause for this many seconds. If 0, pause indefinitely until resume().
        """
        if duration > 0:
            self._paused_until = time.time() + duration
            logger.debug(f"[PassiveLogMonitor] Pausing for {duration}s")
        else:
            self._paused = True
            logger.debug("[PassiveLogMonitor] Paused indefinitely")

    def resume(self):
        """Resume monitoring immediately."""
        self._paused = False
        self._paused_until = 0
        self._last_alert_time = 0.0
        logger.debug("[PassiveLogMonitor] Resumed")

    def _monitor_loop(self):
        """Main monitoring loop."""
        file_path = self._log_file_path
        file_obj = None
        inode = None
        last_ctime = None  # For Windows rotation detection

        try:
            while not self._stop_event.is_set():
                # 1. Check pause state
                if self._paused:
                    time.sleep(self.CHECK_INTERVAL)
                    continue
                
                if self._paused_until > 0:
                    if time.time() < self._paused_until:
                        time.sleep(self.CHECK_INTERVAL)
                        continue
                    else:
                        self._paused_until = 0
                        logger.debug("[PassiveLogMonitor] Pause duration expired, resuming")

                # 2. File handling (Open / Re-open / Rotation check)
                try:
                    if not os.path.exists(file_path):
                        if file_obj:
                            file_obj.close()
                            file_obj = None
                        time.sleep(self.CHECK_INTERVAL)
                        continue

                    stat = os.stat(file_path)
                    current_inode = stat.st_ino if os.name != 'nt' else 0
                    current_size = stat.st_size
                    current_ctime = stat.st_ctime if os.name == 'nt' else 0

                    # First time opening
                    if file_obj is None:
                        file_obj = open(file_path, 'r', encoding='utf-8', errors='ignore')
                        file_obj.seek(0, os.SEEK_END)
                        inode = current_inode
                        last_ctime = current_ctime
                        logger.debug(f"[PassiveLogMonitor] Opened log file: {file_path}")
                    
                    # Check rotation (inode changed, size shrunk, or ctime changed on Windows)
                    elif self._is_file_rotated(inode, current_inode, file_obj.tell(), current_size, last_ctime, current_ctime):
                        logger.debug("[PassiveLogMonitor] Log rotation detected, reopening")
                        file_obj.close()
                        file_obj = open(file_path, 'r', encoding='utf-8', errors='ignore')
                        file_obj.seek(0, os.SEEK_SET)
                        inode = current_inode
                        last_ctime = current_ctime

                    # 3. Read new lines
                    while line := file_obj.readline():
                        if self._stop_event.is_set():
                            break
                        self._process_line(line)

                except Exception as e:
                    logger.error(f"[PassiveLogMonitor] Error reading log: {e}")
                    time.sleep(1.0)

                time.sleep(self.CHECK_INTERVAL)

        finally:
            if file_obj:
                file_obj.close()

    def _is_file_rotated(self, old_inode, new_inode, old_pos, new_size, old_ctime, new_ctime) -> bool:
        """Check if the log file has been rotated."""
        # Unix: inode changed
        if os.name != 'nt' and old_inode != new_inode:
            return True
        # Size shrunk (file was recreated)
        if new_size < old_pos:
            return True
        # Windows: creation time changed
        if os.name == 'nt' and old_ctime and new_ctime and old_ctime != new_ctime:
            return True
        return False

    def _process_line(self, line: str):
        """Process a single log line."""
        lower_line = line.lower()
        
        for keyword in self.ERROR_KEYWORDS:
            if keyword in lower_line:
                logger.debug(f"[PassiveLogMonitor] Keyword '{keyword}' matched in line")
                self._trigger_alert(line.strip())
                break

    def _trigger_alert(self, log_line: str):
        """Trigger an alert if debounce/cooldown allows."""
        now = time.time()
        
        # Debounce check
        if now - self._last_alert_time < self.DEBOUNCE_SECONDS:
            return

        logger.warning(f"[PassiveLogMonitor] Connection failure detected: {log_line}")
        self._last_alert_time = now
        self._consecutive_failures += 1
        
        # Calculate exponential backoff
        backoff = min(
            self.BASE_COOLDOWN_SECONDS * (2 ** (self._consecutive_failures - 1)),
            self.MAX_COOLDOWN_SECONDS
        )
        
        # Auto-pause (Cooldown)
        logger.info(f"[PassiveLogMonitor] Backing off for {backoff}s (Attempt {self._consecutive_failures})")
        self.pause(backoff)

        # Run callback in separate thread to avoid blocking monitor loop
        if self._on_failure:
            threading.Thread(
                target=self._run_callback_safe,
                daemon=True,
                name="PassiveLogMonitor-Callback"
            ).start()

    def _run_callback_safe(self):
        """Run the failure callback safely in a separate thread."""
        try:
            self._on_failure()
        except Exception as e:
            logger.error(f"[PassiveLogMonitor] Error in failure callback: {e}")
