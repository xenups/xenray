"""PingManager - single-flight priority queue controlling all latency tests.

Centralizes every ping operation (manual, import, and background interval) behind
one thread-safe priority queue so only ONE ping operation executes at any given
time. This prevents race conditions, network socket congestion, and overlapping
measurements that would skew delay readings.
"""

from __future__ import annotations

import itertools
import queue as _queue
import threading
from concurrent.futures import Future
from typing import Callable, Optional, Tuple

from src.core.logger import logger

# Priorities: lower number = higher priority.
PRIORITY_MANUAL = 1  # user clicks "Test Ping" — pre-empts imports/intervals
PRIORITY_IMPORT = 2  # auto-pinging newly imported servers / subscriptions
PRIORITY_INTERVAL = 3  # periodic background active-server ping

_Item = Tuple[int, int, str, Callable, Optional[Callable], Optional[Future]]


class PingManager:
    """Thread-safe priority queue executing exactly one ping operation at a time.

    - :meth:`submit` queues a blocking ping operation with a priority + dedup key.
    - :meth:`submit_and_get_future` queues it AND returns a :class:`Future` that
      resolves with ``fn()``'s result (so callers can await the measured ping).
    - A single worker thread pops items in priority order (FIFO within a level).
    - Requests for the same key are deduplicated (never queued/running twice).
    - The interval poller can call :meth:`skip_interval` to skip a cycle while any
      higher-priority (or any pending) work is queued or running.
    """

    def __init__(self) -> None:
        self._queue: _queue.PriorityQueue = _queue.PriorityQueue()
        self._seq = itertools.count()
        self._keys_guard = threading.Lock()
        self._active_keys: set = set()
        self._busy = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._start_lock = threading.Lock()

    # ------------------------------------------------------------------ public
    def submit(
        self,
        priority: int,
        key: str,
        fn: Callable[[], object],
        on_done: Optional[Callable[[object], None]] = None,
    ) -> bool:
        """Queue a ping operation (runs a blocking ``fn``).

        Returns ``False`` if an operation for the same ``key`` is already queued
        or running (deduplicated), otherwise ``True``.
        """
        ok, _ = self._enqueue(priority, key, fn, on_done, None)
        return ok

    def submit_and_get_future(
        self,
        priority: int,
        key: str,
        fn: Callable[[], object],
        on_done: Optional[Callable[[object], None]] = None,
    ) -> Optional[Future]:
        """Queue a ping operation and return a Future resolving with its result.

        Returns ``None`` if the same ``key`` is already queued/running (deduped).
        The future resolves with ``fn()``'s return value (or raises if ``fn``
        raises), so async callers can await the measured result.
        """
        ok, future = self._enqueue(priority, key, fn, on_done, Future())
        return future if ok else None

    def is_busy(self) -> bool:
        """True while any ping operation is queued or running."""
        return self._busy.is_set() or not self._queue.empty()

    def skip_interval(self) -> bool:
        """The interval poller should skip its cycle while any work is pending.

        Prevents a background interval ping from stacking on top of a running
        manual (P1) or import (P2) operation.
        """
        return self.is_busy()

    # -------------------------------------------------------------- internals
    def _enqueue(
        self,
        priority: int,
        key: str,
        fn: Callable[[], object],
        on_done: Optional[Callable[[object], None]],
        future: Optional[Future],
    ) -> Tuple[bool, Optional[Future]]:
        if not key:
            return False, None
        with self._keys_guard:
            if key in self._active_keys:
                return False, None
            self._active_keys.add(key)
        self._start_worker()
        self._queue.put((priority, next(self._seq), key, fn, on_done, future))
        return True, future

    def _start_worker(self) -> None:
        with self._start_lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker.start()

    def _worker_loop(self) -> None:
        while True:
            try:
                item: _Item = self._queue.get(timeout=0.5)
            except _queue.Empty:
                continue
            _, _, key, fn, on_done, future = item
            self._busy.set()
            try:
                result: object = None
                error: Optional[BaseException] = None
                try:
                    result = fn()
                except BaseException as e:  # noqa: BLE001 - keep worker alive
                    error = e
                    logger.error(f"[PingManager] Ping task raised: {e}")

                if future is not None:
                    try:
                        if error is not None:
                            future.set_exception(error)
                        else:
                            future.set_result(result)
                    except Exception:
                        # Caller cancelled/timed out the future (e.g. an
                        # asyncio.wait_for budget expired) — nothing to resolve.
                        pass
                if on_done is not None and error is None:
                    try:
                        on_done(result)
                    except Exception:
                        pass
            finally:
                with self._keys_guard:
                    self._active_keys.discard(key)
                self._busy.clear()


# Process-wide singleton shared by every ping producer.
ping_manager = PingManager()
