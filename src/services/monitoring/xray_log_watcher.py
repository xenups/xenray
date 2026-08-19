"""XrayLogWatcher - reads the Xray core log and publishes events.

Single responsibility: stream the core's stdout/stderr (redirected to a log
file) and surface interesting lines to the event bus. No process management,
no config — just log observation.
"""

from __future__ import annotations

import threading
from typing import Optional

from loguru import logger

from src.core.event_bus import event_bus as default_event_bus


class XrayLogWatcher:
    """Polls a log file tail and publishes parsed events to the event_bus."""

    # Core log lines that carry actionable lifecycle signals (kept simple: the
    # consumers subscribe by engine + phase).
    WATCH_PERIOD = 0.5

    def __init__(self, event_bus=None):
        self._event_bus = event_bus or default_event_bus
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._log_file: Optional[str] = None

    def start(self, log_file: str) -> None:
        """Begin tailing *log_file* in a daemon thread."""
        self._log_file = log_file
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="xray-log-watcher",
        )
        self._thread.start()
        logger.debug(f"[XrayLogWatcher] watching {log_file}")

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def _run(self) -> None:
        # Cheap periodic tail poll; the log file is appended by the core, so we
        # track the byte offset and only surface new content.
        offset = 0
        try:
            while not self._stop.is_set():
                try:
                    with open(self._log_file, "r", errors="replace") as f:
                        f.seek(offset)
                        new = f.read()
                        offset = f.tell()
                    if new:
                        self._emit(new)
                except OSError:
                    pass  # log file not present yet — keep polling
                self._stop.wait(self.WATCH_PERIOD)
        except Exception:  # noqa: BLE001
            logger.debug("[XrayLogWatcher] watcher exited", exc_info=True)

    def _emit(self, chunk: str) -> None:
        """Publish raw log chunks (consumers filter). Extend here if structured
        event parsing is ever required — kept a thin passthrough for now."""
        try:
            self._event_bus.publish("core.log", {"engine": "xray", "chunk": chunk})
        except Exception:  # noqa: BLE001
            pass
