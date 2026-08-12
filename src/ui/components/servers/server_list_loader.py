"""Profile loading / list building for the ServerList component (single-responsibility mixin)."""

from __future__ import annotations
import asyncio
import threading
import time
import flet as ft
from src.core.logger import logger
from src.ui.components.chain.chain_list_item import ChainListItem
from src.ui.components.servers.server_list_item import ServerListItem
from src.ui.components.servers.subscription_list_item import SubscriptionListItem


class ServerListLoaderMixin:
    """Mixin providing ServerList methods — no state of its own."""

    # Progressive-render chunk: only this many ConfigCards are created per
    # micro-batch so a 1000+ server subscription never builds/serializes the
    # whole tree in one event-loop turn (prevents the OSError dataclass crash).
    RENDER_CHUNK = 30

    def _wait_until_added_and_load(self):
        while not self._page:
            try:
                if self.page is not None:
                    break
            except RuntimeError:
                pass
            time.sleep(0.05)
        # Only perform the initial load once. If the list is already populated
        # (e.g. a server was added before this background thread became ready),
        # skip the rebuild — otherwise every card gets re-mounted and the neon
        # inspection animation resets.
        if self._current_list_view is None:
            self._load_profiles(update_ui=True)

    def _create_server_item(self, profile: dict) -> ServerListItem:
        """Build a single ConfigCard without touching the list tree."""
        cached = self._latency_tester.get_cached_result(profile.get("id"))
        return ServerListItem(
            profile=profile,
            on_select=self._select_server,
            on_delete=self._delete_server,
            is_selected=(self._selected_profile_id == profile.get("id")),
            cached_ping=cached,
            is_inspecting=profile.get("id") in self._inspecting_ids,
        )

    def _load_profiles(self, update_ui=False, search_query: str = None):
        """Load and display profiles.

        Large lists are rendered progressively: the first RENDER_CHUNK cards are
        built and swapped in immediately, then the remaining cards are appended
        in micro-chunks on the page event loop (with yields), so building a huge
        subscription never blocks the UI thread or floods Flet's serializer.
        """
        logger.debug("Loading server profiles (update_ui=%s)", update_ui)
        if search_query is not None:
            self._search_query = search_query.strip().lower()

        def _task():
            self._profiles = self._app_context.profiles.load_all()
            self._subscriptions = self._app_context.subscriptions.load_all()
            self._chains = self._app_context.load_chains()
            self._subscriptions.sort(key=lambda x: x.get("name", "").lower())

            # If in subscription view, refresh that instead
            if self._active_subscription:
                fresh_sub = next(
                    (s for s in self._subscriptions if s["id"] == self._active_subscription["id"]),
                    None,
                )
                if fresh_sub:
                    if update_ui:
                        self._ui(lambda: self._enter_subscription_view(fresh_sub))
                    else:
                        self._enter_subscription_view(fresh_sub)
                    return

            if self._search_query:
                self._profiles = [p for p in self._profiles if self._matches_query(p)]
                self._subscriptions = [s for s in self._subscriptions if self._matches_query(s)]

            # Sort profiles
            self._profiles = self._apply_sort(self._profiles)

            # Build list view
            new_list_view = ft.ListView(expand=True, spacing=5, padding=5)
            self._item_map.clear()

            # Add chains first
            logger.info(f"Loading {len(self._chains)} chains into UI")
            for chain in self._chains:
                try:
                    chain_item = ChainListItem(
                        chain=chain,
                        app_context=self._app_context,
                        on_select=self._select_chain,
                        on_edit=self._edit_chain,
                        on_delete=self._delete_chain,
                        is_selected=(self._selected_profile_id == chain.get("id")),
                    )
                    new_list_view.controls.append(chain_item)
                    self._item_map[chain.get("id")] = chain_item
                except Exception as e:
                    logger.error(f"Failed to create ChainListItem for {chain.get('name')}: {e}")

            # Add subscriptions
            for sub in self._subscriptions:
                new_list_view.controls.append(
                    SubscriptionListItem(sub, self._enter_subscription_view, self._delete_subscription)
                )

            # Add profiles — FIRST batch only so the UI displays instantly.
            chunk_size = self.RENDER_CHUNK
            initial_batch = self._profiles[:chunk_size]
            remaining = self._profiles[chunk_size:]
            for profile in initial_batch:
                item = self._create_server_item(profile)
                new_list_view.controls.append(item)
                self._item_map[profile.get("id")] = item

            # Update view
            def _update():
                self._current_list_view = new_list_view
                self._body_switcher.content = new_list_view
                self._body_switcher.update()

            if update_ui:
                self._ui(_update)
            else:
                self._current_list_view = new_list_view
                self._body_switcher.content = new_list_view

            # Progressively inject the remaining cards in background micro-chunks.
            if remaining:
                if self._page is not None:
                    self._schedule_chunked_append(new_list_view, remaining)
                else:
                    # No page yet (early init / tests) — build the rest now.
                    for profile in remaining:
                        item = self._create_server_item(profile)
                        new_list_view.controls.append(item)
                        self._item_map[profile.get("id")] = item

            # Restart testing if it was in progress (Prioritize new sort order)
            if self._latency_tester.is_testing:
                # Filter out already cached profiles to avoid re-testing
                untested = []
                for p in self._profiles:
                    if not self._latency_tester.get_cached_result(p.get("id")):
                        untested.append(p)

                if untested:
                    self._latency_tester.restart_testing(untested)

        if update_ui:
            threading.Thread(target=_task, daemon=True).start()
        else:
            _task()

    def _schedule_chunked_append(self, list_view, remaining_profiles, item_builder=None):
        """Progressively append the remaining profile cards on the page event loop.

        Each micro-chunk builds RENDER_CHUNK ConfigCards, appends them, updates
        ONLY the list view, then yields to the loop (``await asyncio.sleep(0.01)``)
        so a 1000+ subscription never builds/serializes all controls in one turn
        and the Python signal handlers / UI stay fully responsive.
        """
        page = self._page
        if page is None:
            return
        chunk_size = self.RENDER_CHUNK
        builder = item_builder or self._create_server_item

        async def _chunked():
            for i in range(0, len(remaining_profiles), chunk_size):
                chunk = remaining_profiles[i : i + chunk_size]
                try:
                    for profile in chunk:
                        item = builder(profile)
                        list_view.controls.append(item)
                        self._item_map[profile.get("id")] = item
                    try:
                        list_view.update()
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"[ServerList] Chunked append failed: {e}")
                # Yield so the event loop (and signal handlers) stay responsive.
                await asyncio.sleep(0.01)

        try:
            page.run_task(_chunked)
        except Exception:
            pass
