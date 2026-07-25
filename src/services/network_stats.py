"""Network statistics service using threading for efficient I/O-bound monitoring."""
from __future__ import annotations

import queue
import threading
import time
from typing import Optional

from loguru import logger


def _format_speed(bps: float) -> str:
    """Format speed in bps to human readable string."""
    if bps < 1024:
        return f"{bps:.1f} B/s"
    elif bps < 1024 * 1024:
        return f"{bps / 1024:.1f} KB/s"
    elif bps < 1024 * 1024 * 1024:
        return f"{bps / (1024 * 1024):.1f} MB/s"
    else:
        return f"{bps / (1024 * 1024 * 1024):.1f} GB/s"


def _format_bytes(bytes_val: float) -> str:
    """Format total byte count to human readable string."""
    if bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_val / (1024 * 1024 * 1024):.1f} GB"


def _stats_worker(stats_queue: queue.Queue, stop_event: threading.Event):
    """Worker function that runs in a separate thread."""
    import psutil

    last_bytes_sent = 0
    last_bytes_recv = 0
    start_bytes_sent = 0
    start_bytes_recv = 0
    last_time = time.time()

    # Initialize counters
    try:
        counters = psutil.net_io_counters()
        last_bytes_sent = counters.bytes_sent
        last_bytes_recv = counters.bytes_recv
        start_bytes_sent = counters.bytes_sent
        start_bytes_recv = counters.bytes_recv
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
                upload_total_fmt = _format_bytes(max(0, counters.bytes_sent - start_bytes_sent))
                download_total_fmt = _format_bytes(max(0, counters.bytes_recv - start_bytes_recv))

                try:
                    cpu_percent = psutil.cpu_percent()
                    ram_mb = psutil.virtual_memory().used / (1024 * 1024)
                except Exception:
                    cpu_percent = 0.0
                    ram_mb = 0.0

                # Send stats to main thread (non-blocking)
                try:
                    while not stats_queue.empty():
                        try:
                            stats_queue.get_nowait()
                        except queue.Empty:
                            break

                    stats_queue.put_nowait(
                        {
                            "download_speed": download_fmt,
                            "upload_speed": upload_fmt,
                            "download_bps": download_bps,
                            "upload_bps": upload_bps,
                            "total_bps": total_bps,
                            "session_upload": upload_total_fmt,
                            "session_download": download_total_fmt,
                            "cpu_percent": cpu_percent,
                            "ram_mb": ram_mb,
                        }
                    )
                except queue.Full:
                    pass

            last_bytes_sent = counters.bytes_sent
            last_bytes_recv = counters.bytes_recv
            last_time = current_time

        except Exception:
            time.sleep(1)


class NetworkStatsService:
    """Service for monitoring network statistics using a worker thread."""

    def __init__(self):
        self._stats_queue = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._last_stats = {
            "download_speed": "0.0 B/s",
            "upload_speed": "0.0 B/s",
            "total_bps": 0.0,
            "session_upload": "0.0 MB",
            "session_download": "0.0 MB",
        }

    def start(self):
        """Start network monitoring thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=_stats_worker,
            args=(self._stats_queue, self._stop_event),
            daemon=True,
            name="NetworkStatsWorker",
        )
        self._worker_thread.start()
        logger.debug("[NetworkStatsService] Worker thread started")

    def stop(self):
        """Stop network monitoring thread."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
            logger.debug("[NetworkStatsService] Worker thread stopped")

    def get_stats(self) -> dict:
        """Get latest stats (non-blocking). Returns cached stats if no new data."""
        try:
            new_stats = self._stats_queue.get_nowait()
            self._last_stats = new_stats
        except queue.Empty:
            pass

        return self._last_stats
