"""Network Stats Handler - Manages network statistics polling and UI updates."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.core.logger import logger

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class NetworkStatsHandler:
    """Handles network statistics polling and UI updates."""

    def __init__(self, main_window: MainWindow):
        self._main = main_window

    async def run_stats_loop(self):
        """
        Dedicated UI loop for network stats.
        Polls shared state from service and updates UI.
        Runs on main UI thread (Async), does NOT block.
        """
        while True:  # Run continuously, not just when connected
            try:
                # 1. Lifecycle Check (Prevent Race Condition)
                # Ensure StatusDisplay is fully mounted and ready
                if (
                    not self._main._status_display
                    or not self._main._status_display.page
                ):
                    await asyncio.sleep(1.0)
                    continue

                # 2. Update UI
                self._update_ui()

                # 3. Timing Control (Frequency Rule: >= 1s, prefer 1.5s)
                # Moved to end to ensure immediate first update
                await asyncio.sleep(1.5)

            except Exception as e:
                logger.error(f"Error in stats UI loop: {e}")
                await asyncio.sleep(1.5)

    def update_ui_immediately(self):
        """Triggers an immediate UI update if possible."""
        try:
            if self._main._status_display and self._main._status_display.page:
                self._update_ui()
        except Exception as e:
            logger.debug(f"Immediate stats update skipped: {e}")

    def _update_ui(self):
        """Core logic to sync stats with UI components."""
        if not self._main._is_running:
            # Reset heartbeat if needed (idempotent check)
            if self._main._heartbeat and self._main._heartbeat.opacity != 0:
                self._main._heartbeat.opacity = 0
                self._main._heartbeat.update()
            return

        # Read Shared State (Thread-Safe)
        if not self._main._network_stats:
            return

        stats = self._main._network_stats.get_stats()

        # Speeds are pre-formatted strings
        down_str = stats.get("download_speed", "0 B/s")
        up_str = stats.get("upload_speed", "0 B/s")

        try:
            total_bps = float(stats.get("total_bps", 0))
        except (ValueError, TypeError):
            total_bps = 0.0

        # Update Connection Button Glow
        if self._main._connection_button and self._main._connection_button.page:
            self._main._connection_button.update_network_activity(total_bps)

        # Update LogsDrawer stats if open AND mounted
        if (
            self._main._logs_drawer_component
            and self._main._logs_drawer_component.open
            and self._main._logs_drawer_component.page
        ):
            self._main._logs_drawer_component.update_network_stats(down_str, up_str)

        # Earth Glow Animation
        if self._main._earth_glow and self._main._earth_glow.page:
            total_mbps = total_bps / (1024 * 1024)
            intensity = min(1.0, total_mbps / 5.0)

            base_opacity = 0.3
            base_scale = 1.0

            self._main._earth_glow.opacity = base_opacity + (0.5 * intensity)
            self._main._earth_glow.scale = base_scale + (0.2 * intensity)
            self._main._earth_glow.update()

        # Heartbeat logic
        if self._main._logs_heartbeat and self._main._logs_heartbeat.page:
            is_bright = self._main._logs_heartbeat.opacity > 0.5
            self._main._logs_heartbeat.opacity = 0.3 if is_bright else 1.0
            self._main._logs_heartbeat.update()
