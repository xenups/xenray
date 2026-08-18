"""Latency-testing callbacks for the ServerList component."""

from __future__ import annotations

from typing import Optional

import flet as ft

from src.core.i18n import t
from src.core.logger import logger


class ServerListLatencyMixin:
    """Mixin providing ServerList methods — no state of its own."""

    @staticmethod
    def _parse_latency_value(result: str) -> Optional[int]:
        """Extract the numeric latency (ms) from a localized result string."""
        if not result:
            return None
        try:
            import re

            match = re.search(r"(\d+)", result)
            return int(match.group(1)) if match else None
        except Exception:
            return None

    def _test_all_latencies(self):
        """Manually "Ping All": inspect every visible item through the SHARED,
        throttled server_inspector/ping_service pipeline (max 3 concurrent,
        never spawning unbounded Xray/socket runners).

        Results resolve progressively (3-at-a-time) and each completed card is
        updated ONLY via its own TOPIC_SERVER_INSPECTED event — the parent
        ServerList container is never rebuilt.
        """
        from src.services.ping_service import ping_manager
        from src.services.server_inspector import server_inspector

        if ping_manager.is_busy():
            if self._toast:
                self._toast.info(t("server_list.test_in_progress"))
            return

        profiles = [item._profile for item in self._item_map.values()]
        if not profiles:
            return

        # Toggle the header button to "Stop Ping" for the duration of the batch.
        try:
            self._header.set_ping_state(True)
        except Exception:
            pass

        server_inspector.inspect_batch(profiles)

    def _on_latency_test_start(self, profile: dict):
        """Called when a latency test starts for a profile."""
        item = self._item_map.get(profile.get("id"))
        if item:
            self._ui(lambda: item.update_ping(t("server_list.testing"), ft.Colors.BLUE_400))

    def _on_latency_test_complete(self, profile: dict, success: bool, result: str, country_data: Optional[dict]):
        """Called when a latency test completes for a profile."""
        pid = profile.get("id")
        item = self._item_map.get(pid)

        # Update country data if received
        if success and country_data:
            profile.update(country_data)
            if self._active_subscription:
                self._app_context.subscriptions.update(self._active_subscription)
            else:
                self._app_context.profiles.update(pid, country_data)

            # Notify parent
            if self._on_profile_updated:
                self._ui(lambda: self._on_profile_updated(profile))

        # Update item UI
        if item:
            cached = self._latency_tester.get_cached_result(pid)
            if cached:
                self._ui(lambda: item.update_ping(cached[0], cached[1]))

            # Update flag if we got country data
            if success and profile.get("country_code"):
                cc = profile["country_code"]
                cn = profile.get("country_name", cc)
                self._ui(lambda: item.update_icon(cc, cn))

        # Persist latency. atomioc_write_json in file_utils holds a module-level
        # thread lock, so concurrent batch-inspection completions serialize
        # safely — the old "don't persist ping to avoid .tmp collisions" caveat
        # no longer applies. Saving makes the last ping survive page switches and
        # restarts (read from repo on initial list load).
        if pid:
            latency_val = None
            cached = self._latency_tester.get_cached_result(pid)
            if cached:
                latency_val = cached[2]
            elif success:
                latency_val = self._parse_latency_value(result)
            latency_data = {
                "last_latency": result if success else None,
                "last_latency_val": latency_val,
            }
            profile.update(latency_data)
            try:
                if self._active_subscription:
                    self._app_context.subscriptions.update(self._active_subscription, latency_data)
                else:
                    self._app_context.profiles.update(pid, latency_data)
            except Exception as e:
                logger.debug(f"[ServerList] failed to persist ping for {pid}: {e}")

            # Notify parent so a card created later shows the persisted ping.
            if self._on_profile_updated and success:
                try:
                    self._ui(lambda: self._on_profile_updated(profile))
                except Exception:
                    pass

    def _on_all_latency_tests_complete(self):
        """Called when all latency tests are done."""
        if self._active_subscription:
            self._ui(lambda: self._enter_subscription_view(self._active_subscription, preserve_tests=True))
        else:
            self._load_profiles(update_ui=True)
