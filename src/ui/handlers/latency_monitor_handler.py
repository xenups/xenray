"""Latency Monitor Handler - Continuously tests connectivity when disconnected."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from src.core.logger import logger
from src.services.connection_tester import ConnectionTester

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class LatencyMonitorHandler:
    """Handles periodic latency/connectivity checks when disconnected."""

    def __init__(self, main_window: MainWindow):
        self._main = main_window

    async def run_latency_loop(self):
        """Continuously tests connectivity for selected profile when disconnected."""
        while True:
            try:
                if (
                    not self._main._is_running
                    and not self._main._connecting
                    and self._main._selected_profile
                ):
                    await self.trigger_single_check()

                # Check every 60s
                for _ in range(60):
                    await asyncio.sleep(1)

            except Exception as e:
                logger.debug(f"Error in latency monitor loop: {e}")
                await asyncio.sleep(60)

    def trigger_single_check(self):
        """Perform a single latency/connectivity check for the current profile."""
        if not self._main._selected_profile:
            return

        config = self._main._selected_profile.get("config", {})
        profile = self._main._selected_profile

        def on_result(success, result_str, country_data=None):
            # Ensure we still meet conditions when result returns
            if not self._main._is_running and not self._main._connecting:
                self._main._ui_helper.call(
                    self._main._status_display.set_pre_connection_ping,
                    result_str,
                    success,
                )
                # Update country if found
                if country_data and profile:
                    profile.update(country_data)
                    self._main._config_manager.update_profile(
                        profile.get("id"), country_data
                    )
                    # Update display
                    self._main._ui_helper.call(
                        lambda: self._main._server_card.update_server(profile)
                    )

                    if country_data.get("country_code"):
                        self._main._ui_helper.call(
                            self._main._server_list.update_item_icon,
                            profile.get("id"),
                            country_data.get("country_code"),
                        )

        fetch_flag = not profile.get("country_code")
        ConnectionTester.test_connection(config, on_result, fetch_country=fetch_flag)
