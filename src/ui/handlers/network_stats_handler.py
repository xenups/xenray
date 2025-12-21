"""Network Stats Handler - Manages network statistics polling and UI updates."""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

import flet as ft

from src.core.logger import logger
from src.services.network_stats import NetworkStatsService


class NetworkStatsHandler:
    """Handles network statistics polling and UI updates."""

    def __init__(self, network_stats: NetworkStatsService):
        self._network_stats = network_stats
        self._page: Optional[ft.Page] = None
        self._status_display = None
        self._connection_button = None
        self._logs_drawer_component = None
        self._earth_glow = None
        self._logs_heartbeat = None
        self._heartbeat = None

        # State access required for logic
        self._is_running_getter: Optional[Callable[[], bool]] = None

    def setup(
        self,
        page: ft.Page,
        status_display,
        connection_button,
        logs_drawer_component,
        earth_glow,
        logs_heartbeat,
        heartbeat,
        is_running_getter: Callable[[], bool],
    ):
        """Bind UI components and state getters to the handler."""
        self._page = page
        self._status_display = status_display
        self._connection_button = connection_button
        self._logs_drawer_component = logs_drawer_component
        self._earth_glow = earth_glow
        self._logs_heartbeat = logs_heartbeat
        self._heartbeat = heartbeat
        self._is_running_getter = is_running_getter

    async def run_stats_loop(self):
        """
        Dedicated UI loop for network stats.
        Polls shared state from service and updates UI.
        Runs on main UI thread (Async), does NOT block.
        """
        while True:
            try:
                # 1. Lifecycle Check
                if not self._status_display or not self._status_display.page:
                    await asyncio.sleep(1.0)
                    continue

                # 2. Update UI
                self._update_ui()

                # 3. Timing Control
                await asyncio.sleep(1.5)

            except Exception as e:
                logger.error(f"Error in stats UI loop: {e}")
                await asyncio.sleep(1.5)

    def update_ui_immediately(self):
        """Triggers an immediate UI update if possible."""
        try:
            if self._status_display and self._status_display.page:
                self._update_ui()
        except Exception as e:
            logger.debug(f"Immediate stats update skipped: {e}")

    def _update_ui(self):
        """Core logic to sync stats with UI components."""
        is_running = self._is_running_getter() if self._is_running_getter else False

        if not is_running:
            # Reset heartbeat if needed
            if self._heartbeat and self._heartbeat.page and self._heartbeat.opacity != 0:
                self._heartbeat.opacity = 0
                self._heartbeat.update()
            return

        # Read Shared State
        stats = self._network_stats.get_stats()

        # Speeds are pre-formatted strings
        down_str = stats.get("download_speed", "0 B/s")
        up_str = stats.get("upload_speed", "0 B/s")

        try:
            total_bps = float(stats.get("total_bps", 0))
        except (ValueError, TypeError):
            total_bps = 0.0

        # Update Connection Button Glow
        if self._connection_button and self._connection_button.page:
            self._connection_button.update_network_activity(total_bps)

        # Update LogsDrawer stats if open AND mounted
        if self._logs_drawer_component and self._logs_drawer_component.open and self._logs_drawer_component.page:
            self._logs_drawer_component.update_network_stats(down_str, up_str)

        # Earth Glow Animation
        if self._earth_glow and self._earth_glow.page:
            total_mbps = total_bps / (1024 * 1024)
            intensity = min(1.0, total_mbps / 5.0)

            base_opacity = 0.3
            base_scale = 1.0

            # Clamp opacity to valid range [0.0, 1.0]
            calculated_opacity = base_opacity + (0.5 * intensity)
            self._earth_glow.opacity = min(1.0, max(0.0, calculated_opacity))
            self._earth_glow.scale = base_scale + (0.2 * intensity)
            self._earth_glow.update()

        # Heartbeat logic
        if self._logs_heartbeat and self._logs_heartbeat.page:
            is_bright = self._logs_heartbeat.opacity > 0.5
            self._logs_heartbeat.opacity = 0.3 if is_bright else 1.0
            self._logs_heartbeat.update()
