"""Latency Monitor Handler - Continuously tests connectivity when disconnected."""

from __future__ import annotations

import asyncio
import re
from typing import Callable, Optional

import flet as ft

from src.core.app_context import AppContext
from src.core.event_bus import TOPIC_ACTIVE_SERVER_PING_UPDATED, event_bus
from src.core.logger import logger
from src.services.connection_tester import ConnectionTester
from src.services.ping_service import PRIORITY_INTERVAL, ping_manager


class LatencyMonitorHandler:
    """Manages periodic latency checks when disconnected."""

    # Safe polling interval (seconds) between automatic ping scans while
    # disconnected. The PingManager's dedup prevents request stacking.
    PING_INTERVAL_SECONDS = 30

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
        """Periodically test the active server's ping while disconnected."""
        while True:
            try:
                is_running = self._is_running_getter() if self._is_running_getter else False
                connecting = self._connecting_getter() if self._connecting_getter else False
                selected_profile = self._selected_profile_getter() if self._selected_profile_getter else None

                if not is_running and not connecting and selected_profile:
                    # Skip this cycle while a manual (P1) or import (P2) ping is
                    # queued or running — the interval must never stack on top of
                    # higher-priority work (PingManager single-flight lock).
                    if not ping_manager.skip_interval():
                        self.trigger_single_check()

                for _ in range(self.PING_INTERVAL_SECONDS):
                    await asyncio.sleep(1)

            except Exception as e:
                logger.debug(f"Error in latency monitor loop: {e}")
                await asyncio.sleep(self.PING_INTERVAL_SECONDS)

    def _build_active_config(self, profile: dict) -> Optional[dict]:
        """Resolve the config for the active profile (handles chain building)."""
        config = profile.get("config")
        is_chain = profile.get("_is_chain") or profile.get("items") is not None

        if is_chain and (not config or not config.get("outbounds")):
            try:
                from src.services.xray_config_processor import XrayConfigProcessor

                processor = XrayConfigProcessor(self._app_context)
                success, chain_config, error_msg = processor.build_chain_config(profile)
                if success:
                    return chain_config
                logger.warning(f"[LatencyMonitor] Chain config build failed: {error_msg}")
                # Show error in status
                if self._ui_helper and self._status_display:
                    self._ui_helper.call(
                        self._status_display.set_pre_connection_ping,
                        error_msg,
                        False,
                    )
                return None
            except Exception as e:
                logger.error(f"[LatencyMonitor] Failed to build config for chain: {e}")
                return None
        return config

    def run_active_ping_sync(self, profile: dict) -> Optional[tuple]:
        """Run the active-server latency probe synchronously (blocking).

        Returns ``(success, result_str, country_data)`` or ``None`` if the config
        could not be resolved / the probe raised. Does NOT publish — callers route
        the result through :meth:`_on_ping_result` (interval) or the warmup path.
        """
        config = self._build_active_config(profile)
        if config is None:
            return None
        fetch_flag = not profile.get("country_code")
        try:
            success, result_str, country_data = ConnectionTester.test_connection_sync(
                config if config else {},
                fetch_country=fetch_flag,
            )
            return success, result_str, country_data
        except Exception as e:
            logger.debug(f"[LatencyMonitor] Active ping failed: {e}")
            return None

    def trigger_single_check(self):
        """Queue a single latency check for the current profile (PRIORITY_INTERVAL)."""
        profile = self._selected_profile_getter() if self._selected_profile_getter else None
        if not profile:
            return

        pid = str(profile.get("id"))

        def _run():
            result = self.run_active_ping_sync(profile)
            if result:
                self._on_ping_result(profile, *result)

        # Deduplicated by profile id: a pending/running ping for the same server
        # is never re-queued.
        ping_manager.submit(PRIORITY_INTERVAL, f"interval:{pid}", _run)

    def _on_ping_result(
        self,
        profile: dict,
        success: bool,
        result_str: str,
        country_data: Optional[dict],
    ) -> None:
        """Handle a completed ping for the active server (UI update + EventBus)."""
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

        # Broadcast the ping result so DashboardPage can render it live.
        # Marshaled to the UI thread since flet controls are not thread-safe.
        if self._ui_helper:
            self._ui_helper.call(
                lambda: event_bus.publish(
                    TOPIC_ACTIVE_SERVER_PING_UPDATED,
                    {
                        "ping_ms": LatencyMonitorHandler._extract_ping_ms(success, result_str),
                        "success": success,
                        "result_str": result_str,
                    },
                )
            )

    @staticmethod
    def _extract_ping_ms(success: bool, result_str: str) -> Optional[int]:
        """Extract the numeric latency value from a localized result string."""
        if not success:
            return None
        match = re.search(r"(\d+)", result_str)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None
