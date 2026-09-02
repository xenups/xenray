"""Subscription folder navigation + actions for the ServerList component."""

from __future__ import annotations

import flet as ft

from src.core.i18n import t
from src.ui.components.servers.server_list_item import ServerListItem


class ServerListSubscriptionMixin:
    """Mixin providing ServerList methods — no state of its own."""

    def _create_subscription_item(self, profile: dict) -> ServerListItem:
        """Build a read-only ConfigCard for a subscription-folder profile."""
        cached = self._latency_tester.get_cached_result(profile.get("id"))
        return ServerListItem(
            profile=profile,
            on_select=self._select_server,
            is_selected=(self._selected_profile_id == profile.get("id")),
            read_only=True,
            cached_ping=cached,
            is_inspecting=profile.get("id") in self._inspecting_ids,
        )

    def _enter_subscription_view(self, sub: dict, preserve_tests: bool = False):
        """Enter a subscription folder view (progressive/chunked for huge lists)."""
        if not preserve_tests:
            self._latency_tester.cancel()

        self._active_subscription = sub
        self._header.show_subscription_header(sub)

        profiles = self._apply_sort(sub.get("profiles", []))

        sub_list_view = ft.ListView(expand=True, spacing=5, padding=5)
        self._item_map.clear()

        # First batch only — the UI displays instantly.
        chunk_size = self.RENDER_CHUNK
        initial_batch = profiles[:chunk_size]
        remaining = profiles[chunk_size:]
        for profile in initial_batch:
            item = self._create_subscription_item(profile)
            sub_list_view.controls.append(item)
            self._item_map[profile.get("id")] = item

        self._current_list_view = sub_list_view
        self._body_switcher.content = sub_list_view
        try:
            self._body_switcher.update()
        except Exception:
            pass

        # Progressively inject the remaining subscription cards in micro-chunks.
        if remaining:
            self._schedule_chunked_append(sub_list_view, remaining, item_builder=self._create_subscription_item)

        # Restart testing if it was in progress (Prioritize new sort order)
        if self._latency_tester.is_testing:
            # Filter out already cached profiles
            untested = []
            for p in profiles:
                if not self._latency_tester.get_cached_result(p.get("id")):
                    untested.append(p)

            if untested:
                self._latency_tester.restart_testing(untested)

    def _exit_subscription_view(self):
        """Exit subscription view and return to main list.

        Fully resets the subscription-related state so a later
        ``_load_profiles`` (e.g. from a background task) cannot re-enter the
        stale subscription folder:
        - cancels any in-flight latency tests (their results must not land on
          the main list's fresh cards),
        - clears the active subscription + header,
        - reloads the main profile list.
        """
        self._latency_tester.cancel()
        # Defensive: drop any still-queued inspection work for this folder.
        try:
            from src.services.connection.server_inspector import server_inspector

            server_inspector.cancel_all_inspections()
        except Exception:
            pass
        self._active_subscription = None
        self._header.show_main_header()
        self._load_profiles(update_ui=True)

    def _update_subscription(self, sub_id: str):
        """Update a subscription."""
        if not self._page:
            return
        if self._toast:
            self._toast.info(t("server_list.updating_subscription"))

        def callback(success, msg):
            def _ui_update():
                if self._toast:
                    if success:
                        self._toast.success(msg)
                    else:
                        self._toast.error(t("server_list.update_failed", msg=msg))

            self._ui(_ui_update)

        self._subscription_manager.update_subscription(sub_id, callback)

    def _delete_subscription(self, sub_id: str):
        """Delete a subscription."""
        self._app_context.subscriptions.delete(sub_id)
        self._load_profiles(update_ui=True)
        if self._toast:
            self._toast.success(t("server_list.subscription_deleted"))

    def _delete_and_exit_subscription(self, sub_id: str):
        """Delete subscription and exit to main view."""
        self._delete_subscription(sub_id)
        self._active_subscription = None
        self._header.show_main_header()
