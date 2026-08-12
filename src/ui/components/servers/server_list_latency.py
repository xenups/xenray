"""Latency-testing callbacks for the ServerList component."""

from __future__ import annotations
from typing import Optional
import flet as ft
from src.core.i18n import t


class ServerListLatencyMixin:
    """Mixin providing ServerList methods — no state of its own."""

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

        # Update in-memory latency only (volatile UI state — NOT persisted to
        # disk, to avoid `profiles.json.tmp` collisions during large batches).
        if pid:
            latency_data = {
                "last_latency": result if success else None,
                "last_latency_val": self._latency_tester.get_cached_result(pid)[2] if success else None,
            }
            profile.update(latency_data)

    def _on_all_latency_tests_complete(self):
        """Called when all latency tests are done."""
        if self._active_subscription:
            self._ui(lambda: self._enter_subscription_view(self._active_subscription, preserve_tests=True))
        else:
            self._load_profiles(update_ui=True)
