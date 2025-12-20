"""Background Task Handler - Manages background loops and tasks."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import flet as ft

    from src.ui.handlers.latency_monitor_handler import LatencyMonitorHandler
    from src.ui.handlers.network_stats_handler import NetworkStatsHandler


class BackgroundTaskHandler:
    """Manages the lifecycle of background UI tasks and loops."""

    def __init__(
        self,
        network_stats_handler: NetworkStatsHandler,
        latency_monitor_handler: LatencyMonitorHandler,
    ):
        self._page: Optional[ft.Page] = None
        self._network_stats_handler = network_stats_handler
        self._latency_monitor_handler = latency_monitor_handler

    def setup(self, page: ft.Page):
        """Bind UI page to the handler."""
        self._page = page

    def start(self):
        """Start all registered background tasks."""
        if not self._page:
            return
        # Start network stats loop
        self._page.run_task(self._network_stats_handler.run_stats_loop)
        # Start latency monitor loop
        self._page.run_task(self._latency_monitor_handler.run_latency_loop)
