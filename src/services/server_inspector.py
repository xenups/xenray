"""ServerInspector - automatic ping + location inspection for newly imported servers."""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import List, Optional

from src.core.event_bus import TOPIC_SERVER_INSPECTED, event_bus
from src.core.logger import logger
from src.services.connection_tester import ConnectionTester
from src.services.ping_service import PRIORITY_IMPORT, ping_manager


class ServerInspector:
    """Runs ping + geo inspection for imported servers in the background.

    Each inspection measures latency via :class:`ConnectionTester`
    (``fetch_country=True``, so location/flag data is resolved from the ping
    response) and publishes a ``server_inspected`` event over the EventBus so the
    server list can update the specific card live.

    Every inspection is routed through :class:`PingManager` at PRIORITY_IMPORT so
    import pings never overlap a manual test and never run concurrently with the
    background interval poller. Bulk imports run as ONE queued batch (internally
    concurrent via ``asyncio.gather`` with a bounded semaphore), keeping the UI
    thread fully responsive.
    """

    # Upper bound on concurrently spawned per-node tests inside a batch.
    CONCURRENCY_LIMIT = 12

    def inspect(self, profile: Optional[dict]) -> None:
        """Inspect a single server profile through the ping queue (PRIORITY_IMPORT)."""
        if not profile or not profile.get("config"):
            return
        pid = str(profile.get("id"))
        ping_manager.submit(PRIORITY_IMPORT, f"import:{pid}", lambda: self._inspect_sync(profile))

    def inspect_batch(self, profiles: List[dict]) -> None:
        """Inspect many profiles as ONE queued batch (PRIORITY_IMPORT)."""
        if not profiles:
            return

        def _run():
            try:
                asyncio.run(self._inspect_batch_async(profiles))
            except Exception as e:
                logger.error(f"[ServerInspector] Batch inspection error: {e}")

        # Unique batch key so successive import batches never collide on dedup.
        ping_manager.submit(PRIORITY_IMPORT, f"import-batch:{uuid.uuid4()}", _run)

    async def _inspect_batch_async(self, profiles: List[dict]) -> None:
        semaphore = asyncio.Semaphore(self.CONCURRENCY_LIMIT)

        async def _one(profile: dict) -> None:
            async with semaphore:
                await asyncio.to_thread(self._inspect_sync, profile)

        await asyncio.gather(*(_one(p) for p in profiles))

    def _inspect_sync(self, profile: dict) -> None:
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
