"""Network statistics service using threading for efficient I/O-bound monitoring."""

import queue
import threading
import time
from typing import Optional

from loguru import logger


def _stats_worker(stats_queue: queue.Queue, stop_event: threading.Event):
    """Worker function that runs in a separate thread."""
    import psutil

    last_bytes_sent = 0
    last_bytes_recv = 0
    last_time = time.time()

    # Initialize counters
    try:
        counters = psutil.net_io_counters()
        last_bytes_sent = counters.bytes_sent
        last_bytes_recv = counters.bytes_recv
    except Exception:
        pass

    while not stop_event.is_set():
        try:
            time.sleep(1.5)  # Collection interval

            if stop_event.is_set():
                break

            counters = psutil.net_io_counters()
            current_time = time.time()
            elapsed = current_time - last_time

            if elapsed > 0:
                download_bps = (counters.bytes_recv - last_bytes_recv) / elapsed
                upload_bps = (counters.bytes_sent - last_bytes_sent) / elapsed
                total_bps = download_bps + upload_bps

                download_fmt = _format_speed(download_bps)
                upload_fmt = _format_speed(upload_bps)

                # Send stats to main thread (non-blocking)
                try:
                    # Clear old data if queue is full
                    while not stats_queue.empty():
                        try:
                            stats_queue.get_nowait()
                        except queue.Empty:
                            break

                    stats_queue.put_nowait(
                        {
                            "download_speed": download_fmt,
                            "upload_speed": upload_fmt,
                            "total_bps": total_bps,
                        }
                    )
                except queue.Full:
                    pass  # Queue full, skip this update

            last_bytes_sent = counters.bytes_sent
            last_bytes_recv = counters.bytes_recv
            last_time = current_time

        except Exception:
            time.sleep(1)


def _format_speed(bytes_per_sec: float) -> str:
    """Format bytes per second to human readable string."""
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    elif bytes_per_sec < 1024 * 1024 * 1024:
        return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024 * 1024):.2f} GB/s"


class NetworkStatsService:
    """Service to monitor network upload and download speeds using threading."""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._queue: Optional[queue.Queue] = None
        self._stop_event: Optional[threading.Event] = None
        self._running = False
        self._lock = threading.Lock()  # Thread safety for start/stop

        # Cached stats (read from queue)
        self._cached_stats = {
            "download_speed": "0 B/s",
            "upload_speed": "0 B/s",
            "total_bps": 0.0,
        }

    def start(self):
        """Start monitoring network stats in a separate thread."""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._queue = queue.Queue(maxsize=5)
            self._stop_event = threading.Event()

            self._thread = threading.Thread(
                target=_stats_worker,
                args=(self._queue, self._stop_event),
                daemon=True,
                name="NetworkStatsWorker",
            )
            self._thread.start()
            logger.debug("[NetworkStats] Started monitoring (Threading)")

    def stop(self):
        """Stop monitoring network stats."""
        with self._lock:
            if not self._running:
                return

            self._running = False

            if self._stop_event:
                self._stop_event.set()

            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2)
                if self._thread.is_alive():
                    logger.warning("[NetworkStats] Thread did not stop cleanly")

            self._thread = None
            self._queue = None
            self._stop_event = None
            logger.debug("[NetworkStats] Stopped monitoring")

    def get_stats(self) -> dict:
        """Get latest stats (non-blocking read from queue)."""
        if self._queue:
            try:
                # Read all available updates, keep the latest
                while not self._queue.empty():
                    self._cached_stats = self._queue.get_nowait()
            except queue.Empty:
                pass

        return self._cached_stats.copy()
