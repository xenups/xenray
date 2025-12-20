"""Network statistics service using multiprocessing to avoid blocking main thread."""

import multiprocessing
import time
from multiprocessing import Process, Queue
from typing import Optional

from loguru import logger


def _stats_worker(queue: Queue, stop_event: multiprocessing.Event):
    """Worker function that runs in a separate process."""
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

                # Send stats to main process (non-blocking)
                try:
                    # Clear old data if queue is full
                    while not queue.empty():
                        try:
                            queue.get_nowait()
                        except Exception:
                            break

                    queue.put_nowait(
                        {
                            "download_speed": download_fmt,
                            "upload_speed": upload_fmt,
                            "total_bps": total_bps,
                        }
                    )
                except Exception:
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
    """Service to monitor network upload and download speeds using multiprocessing."""

    def __init__(self):
        self._process: Optional[Process] = None
        self._queue: Optional[Queue] = None
        self._stop_event: Optional[multiprocessing.Event] = None
        self._running = False

        # Cached stats (read from queue)
        self._cached_stats = {
            "download_speed": "0 B/s",
            "upload_speed": "0 B/s",
            "total_bps": 0.0,
        }

    def start(self):
        """Start monitoring network stats in a separate process."""
        if self._running:
            return

        self._running = True
        self._queue = Queue(maxsize=5)
        self._stop_event = multiprocessing.Event()

        self._process = Process(target=_stats_worker, args=(self._queue, self._stop_event), daemon=True)
        self._process.start()
        logger.debug("[NetworkStats] Started monitoring (Multiprocessing)")

    def stop(self):
        """Stop monitoring network stats."""
        self._running = False

        if self._stop_event:
            self._stop_event.set()

        if self._process and self._process.is_alive():
            self._process.join(timeout=2)
            if self._process.is_alive():
                self._process.terminate()

        self._process = None
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
            except Exception:
                pass

        return self._cached_stats.copy()
