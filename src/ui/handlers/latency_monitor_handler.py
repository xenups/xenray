"""Latency Monitor Handler - Continuously tests connectivity when disconnected."""

from __future__ import annotations

import asyncio
from typing import Callable, Optional

import flet as ft

from src.core.app_context import AppContext
from src.core.logger import logger
from src.services.connection_tester import ConnectionTester


class LatencyMonitorHandler:
    """Manages periodic latency checks when disconnected."""

    def __init__(self, app_context: AppContext):
        self._app_context = app_context
        self._page: Optional[ft.Page] = None
        self._status_display = None
        self._server_card = None
        self._server_list = None
        self._ui_helper = None

        # State access required for logic
        self._is_running_getter: Optional[Callable[[], bool]] = None
        self._connecting_getter: Optional[Callable[[], bool]] = None
        self._selected_profile_getter: Optional[Callable[[], Optional[dict]]] = None

    def setup(
        self,
        page: ft.Page,
        status_display,
        server_card,
        server_list,
        ui_helper,
        is_running_getter: Callable[[], bool],
        connecting_getter: Callable[[], bool],
        selected_profile_getter: Callable[[], Optional[dict]],
    ):
        """Bind UI components and state getters to the handler."""
        self._page = page
        self._status_display = status_display
        self._server_card = server_card
        self._server_list = server_list
        self._ui_helper = ui_helper
        self._is_running_getter = is_running_getter
        self._connecting_getter = connecting_getter
        self._selected_profile_getter = selected_profile_getter

    async def run_latency_loop(self):
        """Continuously tests connectivity for selected profile when disconnected."""
        while True:
            try:
                is_running = self._is_running_getter() if self._is_running_getter else False
                connecting = self._connecting_getter() if self._connecting_getter else False
                selected_profile = self._selected_profile_getter() if self._selected_profile_getter else None

                if not is_running and not connecting and selected_profile:
                    self.trigger_single_check()

                # Check every 60s
                for _ in range(60):
                    await asyncio.sleep(1)

            except Exception as e:
                logger.debug(f"Error in latency monitor loop: {e}")
                await asyncio.sleep(60)

    def trigger_single_check(self):
        """Perform a single latency/connectivity check for the current profile."""
        profile = self._selected_profile_getter() if self._selected_profile_getter else None
        if not profile:
            return

        config = profile.get("config")
        is_chain = profile.get("_is_chain") or profile.get("items") is not None

        # Build chain config if needed
        if is_chain and (not config or not config.get("outbounds")):
            try:
                from src.services.xray_config_processor import XrayConfigProcessor

                processor = XrayConfigProcessor(self._app_context)
                success, chain_config, error_msg = processor.build_chain_config(profile)
                if success:
                    config = chain_config
                else:
                    logger.warning(f"[LatencyMonitor] Chain config build failed: {error_msg}")
                    # Show error in status
                    if self._ui_helper and self._status_display:
                        self._ui_helper.call(
                            self._status_display.set_pre_connection_ping,
                            error_msg,
                            False,
                        )
                    return
            except Exception as e:
                logger.error(f"[LatencyMonitor] Failed to build config for chain: {e}")
                return

        def on_result(success, result_str, country_data=None):
            is_running = self._is_running_getter() if self._is_running_getter else False
            connecting = self._connecting_getter() if self._connecting_getter else False

            # Ensure we still meet conditions when result returns
            if not is_running and not connecting:
                if self._ui_helper and self._status_display:
                    self._ui_helper.call(
                        self._status_display.set_pre_connection_ping,
                        result_str,
                        success,
                    )
                # Update country if found
                if country_data and profile:
                    profile.update(country_data)
                    self._app_context.profiles.update(profile.get("id"), country_data)
                    # Update display
                    if self._ui_helper:
                        if self._server_card:
                            self._ui_helper.call(lambda: self._server_card.update_server(profile))

                        if country_data.get("country_code") and self._server_list:
                            self._ui_helper.call(
                                self._server_list.update_item_icon,
                                profile.get("id"),
                                country_data.get("country_code"),
                            )

        fetch_flag = not profile.get("country_code")
        ConnectionTester.test_connection(config if config else {}, on_result, fetch_country=fetch_flag)
