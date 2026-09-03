"""Auto-inspection live-update handlers for the ServerList component."""

from __future__ import annotations

from typing import Optional

import flet as ft

from src.core.logger import logger


class ServerListEventsMixin:
    """Mixin providing ServerList methods — no state of its own."""

    def update_item_icon(self, profile_id: str, country_code: str):
        """Update the icon for a specific profile (called from MainWindow)."""
        item = self._item_map.get(profile_id)
        if item:
            item.update_icon(country_code)

    def _cancel_ping_all(self):
        """User clicked 'Stop Ping' — cancel all in-flight inspection tasks and
        stop the neon sweeps on active cards."""
        from src.services.connection.server_inspector import server_inspector

        server_inspector.cancel_all_inspections()
        # Revert the header button immediately (the batch-completed event is the
        # fallback for normal completion).
        try:
            self._header.set_ping_state(False)
        except Exception:
            pass

    def _on_inspection_batch_completed(self, data=None) -> None:
        """Batch inspection finished OR was canceled: revert the Ping All button
        and stop any neon sweeps still running on cards (canceled mid-probe)."""
        try:
            self._ui(lambda: self._header.set_ping_state(False))
        except Exception:
            pass
        for item in self._item_map.values():
            if hasattr(item, "stop_inspection_animation"):
                try:
                    self._ui(lambda it=item: it.stop_inspection_animation())
                except Exception:
                    pass

    def _on_server_inspecting(self, data) -> None:
        """A server inspection began — start ONLY that card's neon sweep.

        Single centralized subscriber: the target card is resolved via
        ``_item_map`` and its public ``start_inspection_animation`` is called
        directly (no per-card EventBus subscription).
        """
        if not isinstance(data, dict):
            return
        server_id = data.get("server_id")
        if not server_id:
            return
        logger.debug(f"[ServerList] _on_server_inspecting for {server_id}")
        self._inspecting_ids.add(str(server_id))

        item = self._item_map.get(server_id)
        if item is not None and hasattr(item, "start_inspection_animation"):
            self._ui(lambda: item.start_inspection_animation())

    def _on_server_inspected(self, data) -> None:
        """Update the specific server card live when an import inspection finishes
        (stop its neon sweep, then update ONLY its ping/icon badge)."""
        if not isinstance(data, dict):
            return
        server_id = data.get("server_id")
        if not server_id:
            return
        logger.debug(f"[ServerList] _on_server_inspected for {server_id}")
        self._inspecting_ids.discard(str(server_id))

        success = data.get("success", False)
        result_str = data.get("result_str")
        location = data.get("location") or {}
        ping_ms = data.get("ping")

        # Persist ONLY stable metadata (country/city) PLUS the resolved ping.
        # Latency was historically kept in-memory to avoid cross-thread writes
        # during a big batch, but atomic_write_json already serialises writers
        # via a module-level lock, so persisting ping is safe and makes the last
        # ping survive page switches and restarts.
        persist_updates: dict = {}
        if location.get("country_code"):
            persist_updates["country_code"] = location["country_code"]
            persist_updates["country_name"] = location.get("country_name", location["country_code"])
            if location.get("city"):
                persist_updates["city"] = location.get("city")
        if ping_ms is not None and success:
            persist_updates["last_latency_val"] = ping_ms
            if result_str:
                persist_updates["last_latency"] = result_str
        if persist_updates:
            self._persist_profile_updates(server_id, persist_updates)

        # In-memory model update (volatile ping + stable location). Applied to the
        # profile MODEL first so a card created LATER (chunked rendering) still
        # shows the resolved ping; then to the live card if it exists.
        in_memory = dict(persist_updates)
        if result_str:
            in_memory["last_latency"] = result_str if success else None
            in_memory["last_latency_val"] = ping_ms if success else None
        self._update_profile_model(server_id, in_memory)

        item = self._item_map.get(server_id)
        if item is None:
            return
        if hasattr(item, "_profile"):
            item._profile.update(in_memory)

        # Stop the sweep on this card first (the batch worker has released its slot).
        if hasattr(item, "stop_inspection_animation"):
            self._ui(lambda: item.stop_inspection_animation())

        if result_str and hasattr(item, "update_ping"):
            color = self._inspection_color(success, ping_ms)
            self._ui(lambda: item.update_ping(result_str, color))

        if location.get("country_code") and hasattr(item, "update_icon"):
            cc = location["country_code"]
            cn = location.get("country_name", cc)
            self._ui(lambda: item.update_icon(cc, cn))

    def _update_profile_model(self, server_id: str, updates: dict) -> None:
        """Apply volatile results to the in-memory profile model in ANY list
        (main list or active subscription), even before its card is created."""
        target_lists = []
        if self._active_subscription:
            target_lists.append(self._active_subscription.get("profiles", []))
        else:
            target_lists.append(self._profiles)
        for profiles in target_lists:
            for p in profiles:
                if str(p.get("id")) == str(server_id):
                    p.update(updates)
                    return

    @staticmethod
    def _inspection_color(success: bool, ping_ms: Optional[int]) -> str:
        """Map an inspection result to a ping badge color."""
        if not success or ping_ms is None:
            return ft.Colors.RED_400
        if ping_ms < 1000:
            return ft.Colors.GREEN_400
        if ping_ms < 2000:
            return ft.Colors.ORANGE_400
        return ft.Colors.RED_400

    def _persist_profile_updates(self, pid: str, updates: dict) -> None:
        """Persist inspection results to the owning repository (profiles or subscription)."""
        try:
            if self._app_context.profiles.get_by_id(pid):
                self._app_context.profiles.update(pid, updates)
                return
            for sub in self._app_context.subscriptions.load_all():
                for profile in sub.get("profiles", []):
                    if profile.get("id") == pid:
                        profile.update(updates)
                        self._app_context.subscriptions.update(sub)
                        return
        except Exception:
            pass
