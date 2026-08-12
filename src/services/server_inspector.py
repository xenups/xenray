"""ServerInspector - automatic ping + location inspection for newly imported servers."""

from __future__ import annotations

import asyncio
import re
import threading
import uuid
from typing import List, Optional

from src.core.event_bus import (
    TOPIC_INSPECTION_BATCH_COMPLETED,
    TOPIC_SERVER_INSPECTED,
    TOPIC_SERVER_INSPECTING,
    event_bus,
)
from src.core.logger import logger
from src.services.connection_tester import ConnectionTester
from src.services.ping_service import PRIORITY_IMPORT, ping_manager

# Auto-inspection threshold: subscriptions/batches with MORE than this many
# servers skip automatic pinging entirely (idle / uninspected) — pings only run
# when the user manually triggers them (Ping button / Ping All).
AUTO_INSPECT_LIMIT = 20


class ServerInspector:
    """Runs ping + geo inspection for imported servers in the background.

    Each inspection measures latency via :class:`ConnectionTester`
    (``fetch_country=True``, so location/flag data is resolved from the ping
    response). A ``server_inspecting`` event is published when the inspection is
    submitted (immediately, so the UI can show the animated inspection state) and
    again when it actually begins; a ``server_inspected`` event is published when
    it finishes.

    Every inspection is routed through :class:`PingManager` at PRIORITY_IMPORT so
    import pings never overlap a manual test and never run concurrently with the
    background interval poller. Bulk imports run as ONE queued batch (internally
    concurrent via ``asyncio.gather`` with a bounded semaphore), keeping the UI
    thread fully responsive.
    """

    # Strict cap on concurrently spawned per-node tests inside a batch — never
    # run more than 3 Xray/socket runners at once to avoid CPU/network spikes.
    CONCURRENCY_LIMIT = 3

    def __init__(self) -> None:
        # Active inspection task references (batch worker) for cancellation.
        self._active_tasks: set = set()
        self._master_ping_task: Optional[asyncio.Task] = None
        self._active_loop: Optional[asyncio.AbstractEventLoop] = None
        # Cross-thread cancel flag checked by the sync probe runner.
        self._cancel_event = threading.Event()

    def inspect(self, profile: Optional[dict]) -> None:
        """Inspect a single server profile through the ping queue (PRIORITY_IMPORT).

        A ``server_inspecting`` event is published synchronously at submission
        so the UI can start the neon sweep the moment a config is added, without
        waiting for the ping queue to actually begin processing.
        """
        if not profile or not profile.get("config"):
            return
        pid = str(profile.get("id"))
        event_bus.publish(TOPIC_SERVER_INSPECTING, {"server_id": pid})
        ping_manager.submit(PRIORITY_IMPORT, f"import:{pid}", lambda: self._inspect_sync(profile))

    def inspect_batch(self, profiles: List[dict]) -> None:
        """Inspect many profiles as ONE queued batch (PRIORITY_IMPORT).

        The ``server_inspecting`` / ``server_inspected`` events are published
        ONLY from inside the bounded Semaphore worker loop — i.e. a card's neon
        sweep starts when its task acquires the semaphore lock (max 3 active at
        once) and stops when it completes. Cards waiting in the queue stay
        completely idle until their turn.
        """
        if not profiles:
            return

        def _run():
            try:
                asyncio.run(self._inspect_batch_async(profiles))
            except asyncio.CancelledError:
                # User canceled the batch — handled cleanly (batch_completed event
                # already fired from the finally block).
                logger.debug("[ServerInspector] Batch inspection canceled")
            except Exception as e:
                logger.error(f"[ServerInspector] Batch inspection error: {e}")

        # Unique batch key so successive import batches never collide on dedup.
        ping_manager.submit(PRIORITY_IMPORT, f"import-batch:{uuid.uuid4()}", _run)

    async def _inspect_batch_async(self, profiles: List[dict]) -> None:
        # Track the master asyncio.run() task so cancel_all_inspections() can
        # terminate the WHOLE batch (gather + semaphore holders) instantly,
        # releasing the single-flight ping worker so a new Ping All starts at once.
        self._master_ping_task = asyncio.current_task()
        self._active_loop = asyncio.get_running_loop()
        self._cancel_event.clear()

        semaphore = asyncio.Semaphore(self.CONCURRENCY_LIMIT)

        async def _one(profile: dict) -> None:
            async with semaphore:
                if self._cancel_event.is_set():
                    return
                await asyncio.to_thread(self._inspect_sync, profile)

        tasks = [asyncio.create_task(_one(p)) for p in profiles]
        for t in tasks:
            self._active_tasks.add(t)
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            # Cancellation is intentional (Stop Ping) — propagate it so the
            # asyncio.run() worker terminates immediately. Subprocess/socket
            # cleanup happens inside test_connection_sync's finally block.
            raise
        finally:
            for t in tasks:
                self._active_tasks.discard(t)
            self._active_tasks.clear()
            self._master_ping_task = None
            self._active_loop = None
            self._cancel_event.clear()
            # Signal the UI that the batch finished (or was canceled) so the
            # "Ping All" button can revert to its idle state.
            event_bus.publish(TOPIC_INSPECTION_BATCH_COMPLETED, {"canceled": False})

    def cancel_all_inspections(self) -> None:
        """Cancel all in-flight inspection tasks (thread-safe) and stop any
        remaining neon sweeps via the batch-completed signal.

        Cancels the MASTER batch task first — this propagates cancellation
        through ``asyncio.gather`` to every ``_one`` worker, releasing the
        semaphore holders and letting the ``asyncio.run`` worker terminate so
        the single-flight ping manager frees up immediately.
        """
        self._cancel_event.set()
        loop = self._active_loop
        master = self._master_ping_task

        def _schedule_cancel(task):
            try:
                if loop is not None and not task.done():
                    loop.call_soon_threadsafe(task.cancel)
                elif not task.done():
                    task.cancel()
            except Exception:
                pass

        if master is not None:
            _schedule_cancel(master)
        for task in list(self._active_tasks):
            _schedule_cancel(task)
        self._active_tasks.clear()
        self._active_loop = None
        event_bus.publish(TOPIC_INSPECTION_BATCH_COMPLETED, {"canceled": True})

    def _inspect_sync(self, profile: dict) -> None:
        # If the user hit "Stop", skip probes that haven't started yet.
        if self._cancel_event.is_set():
            return
        # Signal the UI that this server's inspection has begun so its config
        # card can start the neon sweep animation (before the ping result lands).
        event_bus.publish(
            TOPIC_SERVER_INSPECTING,
            {"server_id": profile.get("id")},
        )
        try:
            config = profile.get("config") or {}
            success, result_str, country_data = ConnectionTester.test_connection_sync(config, fetch_country=True)

            ping_ms: Optional[int] = None
            if success:
                match = re.search(r"(\d+)", result_str)
                if match:
                    try:
                        ping_ms = int(match.group(1))
                    except ValueError:
                        pass

            event_bus.publish(
                TOPIC_SERVER_INSPECTED,
                {
                    "server_id": profile.get("id"),
                    "ping": ping_ms,
                    "location": country_data or {},
                    "success": success,
                    "result_str": result_str,
                },
            )
        except Exception as e:
            logger.error(f"[ServerInspector] Inspection failed for {profile.get('id')}: {e}")


# Process-wide singleton so every import entry point shares the same service.
server_inspector = ServerInspector()
