"""Thread-safe Server List component for XenRay."""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import flet as ft

from src.core.app_context import AppContext
from src.core.i18n import t
from src.core.logger import logger
from src.core.subscription_manager import SubscriptionManager
from src.services.latency_tester import LatencyTester
from src.ui.components.add_server_dialog import AddServerDialog
from src.ui.components.chain_list_item import ChainListItem
from src.ui.components.server_list_header import ServerListHeader
from src.ui.components.server_list_item import ServerListItem
from src.ui.components.subscription_list_item import SubscriptionListItem
from src.ui.pages.chain_builder_page import ChainBuilderPage


class ServerList(ft.Container):
    """Thread-safe Server List component for XenRay."""

    def __init__(
        self,
        app_context: AppContext,
        on_server_selected: Callable,
        on_profile_updated: Callable = None,
        toast_manager=None,
        navigate_to: Callable = None,
        navigate_back: Callable = None,
        close_sheet: Callable = None,
    ):
        self._app_context = app_context
        self._subscription_manager = SubscriptionManager(app_context)
        self._on_server_selected = on_server_selected
        self._on_profile_updated = on_profile_updated
        self._toast = toast_manager
        self._navigate_to = navigate_to
        self._navigate_back = navigate_back
        self._close_sheet = close_sheet

        # Data
        self._profiles: list[dict] = []
        self._subscriptions: list[dict] = []
        self._chains: list[dict] = []

        # State
        self._page: Optional[ft.Page] = None
        self._current_list_view = None
        self._selected_profile_id = self._app_context.settings.get_last_selected_profile_id()  # Load last selected
        self._active_subscription = None

        # Item tracking for updates
        self._item_map: dict[str, ServerListItem] = {}

        # Latency Tester
        self._latency_tester = LatencyTester(
            on_test_start=self._on_latency_test_start,
            on_test_complete=self._on_latency_test_complete,
            on_all_complete=self._on_all_latency_tests_complete,
            app_context=self._app_context,
        )

        # Header Component
        self._header = ServerListHeader(
            get_sort_mode=self._app_context.settings.get_sort_mode,
            set_sort_mode=self._on_sort_changed,
            on_test_latency=self._test_all_latencies,
            on_add_click=self._show_add_dialog,
            on_back_click=self._exit_subscription_view,
            on_update_subscription=self._update_subscription,
            on_delete_subscription=self._delete_and_exit_subscription,
        )

        # Add Dialog
        self._add_dialog = AddServerDialog(
            on_server_added=self._handle_server_added,
            on_subscription_added=self._handle_subscription_added,
            on_close=self._close_add_dialog,
            on_create_chain=self.show_chain_builder,
        )

        # Animated Body Switcher
        self._body_switcher = ft.AnimatedSwitcher(
            content=ft.Container(),
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=150,
            reverse_duration=150,
            switch_in_curve=ft.AnimationCurve.EASE_IN,
            switch_out_curve=ft.AnimationCurve.EASE_OUT,
            expand=True,
        )

        super().__init__(
            content=ft.Column(
                [
                    self._header,
                    ft.Container(height=5),
                    ft.Container(content=self._body_switcher, expand=True),
                ],
                spacing=0,
            ),
            padding=5,
            bgcolor=ft.Colors.with_opacity(0.15, "#0f172a"),  # More transparent
            blur=ft.Blur(25, 25, ft.BlurTileMode.MIRROR),  # Higher blur
            border_radius=ft.border_radius.only(top_left=20, top_right=20),
            expand=True,
        )

    # --- Page Management ---
    def set_page(self, page: ft.Page):
        self._page = page
        threading.Thread(target=self._wait_until_added_and_load, daemon=True).start()

    def _wait_until_added_and_load(self):
        while not self._page or not self.page:
            time.sleep(0.05)
        self._load_profiles(update_ui=True)

    def _ui(self, fn: Callable):
        """Execute a function on the UI thread."""
        if not self._page:
            return

        async def _coro():
            try:
                fn()
            except Exception as e:
                logger.debug(f"UI update error: {e}")

        self._page.run_task(_coro)

    # --- Sort Handling ---
    def _on_sort_changed(self, mode: str):
        """Handle sort mode change."""
        self._app_context.settings.set_sort_mode(mode)
        if self._active_subscription:
            self._enter_subscription_view(self._active_subscription, preserve_tests=True)
        else:
            self._load_profiles(update_ui=True)

    def _apply_sort(self, items: list) -> list:
        """Apply current sort mode to items."""
        mode = self._app_context.settings.get_sort_mode()

        def get_latency(item):
            pid = item.get("id")
            cached = self._latency_tester.get_cached_result(pid)
            if cached:
                return cached[2]  # latency_val
            # Fallback to saved latency
            val = item.get("last_latency_val")
            return val if val is not None else 999999

        if mode == "name_asc":
            return sorted(items, key=lambda x: x.get("name", "").lower())
        if mode == "ping_asc":
            return sorted(items, key=get_latency)
        return items

    # --- Profile Loading ---
    def _load_profiles(self, update_ui=False):
        """Load and display profiles."""

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

            # Sort profiles
            self._profiles = self._apply_sort(self._profiles)

            # Build list view
            new_list_view = ft.ListView(expand=True, spacing=5, padding=5)
            self._item_map.clear()

            # Add chains first
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

            # Add profiles
            for profile in self._profiles:
                cached = self._latency_tester.get_cached_result(profile.get("id"))
                item = ServerListItem(
                    profile=profile,
                    on_select=self._select_server,
                    on_delete=self._delete_server,
                    is_selected=(self._selected_profile_id == profile.get("id")),
                    cached_ping=cached,
                )
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

    # --- Subscription Navigation ---
    def _enter_subscription_view(self, sub: dict, preserve_tests: bool = False):
        """Enter a subscription folder view."""
        if not preserve_tests:
            self._latency_tester.cancel()

        self._active_subscription = sub
        self._header.show_subscription_header(sub)

        profiles = self._apply_sort(sub.get("profiles", []))

        sub_list_view = ft.ListView(expand=True, spacing=5, padding=5)
        self._item_map.clear()

        for profile in profiles:
            cached = self._latency_tester.get_cached_result(profile.get("id"))
            item = ServerListItem(
                profile=profile,
                on_select=self._select_server,
                is_selected=(self._selected_profile_id == profile.get("id")),
                read_only=True,
                cached_ping=cached,
            )
            sub_list_view.controls.append(item)
            self._item_map[profile.get("id")] = item

        self._current_list_view = sub_list_view
        self._body_switcher.content = sub_list_view
        try:
            self._body_switcher.update()
        except Exception:
            pass

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
        """Exit subscription view and return to main list."""
        self._latency_tester.cancel()
        self._active_subscription = None
        self._header.show_main_header()
        self._load_profiles(update_ui=True)

    # --- Latency Testing ---
    def _test_all_latencies(self):
        """Start latency test for all visible items."""
        if self._latency_tester.is_testing:
            if self._toast:
                self._toast.info(t("server_list.test_in_progress"))
            return

        profiles = []
        for profile_id, item in self._item_map.items():
            profiles.append(item._profile)

        if not profiles:
            return

        self._latency_tester.test_profiles(profiles)

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

        # Persist latency
        if pid:
            latency_data = {
                "last_latency": result if success else None,
                "last_latency_val": self._latency_tester.get_cached_result(pid)[2] if success else None,
            }
            if self._active_subscription:
                profile.update(latency_data)  # Update reference inside subscription
                self._app_context.subscriptions.update(self._active_subscription)
            else:
                self._app_context.profiles.update(pid, latency_data)

    def _on_all_latency_tests_complete(self):
        """Called when all latency tests are done."""
        if self._page:
            self._ui(lambda: self._page.update())

    def update_item_icon(self, profile_id: str, country_code: str):
        """Update the icon for a specific profile (called from MainWindow)."""
        item = self._item_map.get(profile_id)
        if item:
            item.update_icon(country_code)

    # --- Server Actions ---
    def _select_server(self, profile: dict):
        """Handle server selection."""
        self._selected_profile_id = profile["id"]
        if self._on_server_selected:
            self._on_server_selected(profile)
        self._load_profiles(update_ui=True)

    def _delete_server(self, profile_id: str):
        """Delete a server profile."""
        self._app_context.profiles.delete(profile_id)
        self._load_profiles(update_ui=True)
        if self._page:
            if self._toast:
                self._toast.success(t("server_list.server_deleted"))
            self._page.update()

    # --- Subscription Actions ---
    def _update_subscription(self, sub_id: str):
        """Update a subscription."""
        if not self._page:
            return
        if self._toast:
            self._toast.info(t("server_list.updating_subscription"))
        self._page.update()

        def callback(success, msg):
            def _ui_update():
                if self._toast:
                    if success:
                        self._toast.success(msg)
                    else:
                        self._toast.error(t("server_list.update_failed", msg=msg))
                self._page.update()

            self._ui(_ui_update)

        self._subscription_manager.update_subscription(sub_id, callback)

    def _delete_subscription(self, sub_id: str):
        """Delete a subscription."""
        self._app_context.subscriptions.delete(sub_id)
        self._load_profiles(update_ui=True)
        if self._page:
            if self._toast:
                self._toast.success(t("server_list.subscription_deleted"))
            self._page.update()

    def _delete_and_exit_subscription(self, sub_id: str):
        """Delete subscription and exit to main view."""
        self._delete_subscription(sub_id)
        self._active_subscription = None
        self._header.show_main_header()

    # --- Add Dialog ---
    def _show_add_dialog(self, e=None):
        """Show the add server/subscription dialog."""
        if self._page:
            self._page.open(self._add_dialog)
            self._page.update()

    def _close_add_dialog(self):
        """Close the add dialog."""
        if self._page:
            self._page.close(self._add_dialog)
            self._page.update()

    def _handle_server_added(self, name: str, config: dict):
        """Handle a new server being added."""
        self._app_context.profiles.save(name, config)
        if self._toast:
            self._toast.success(t("add_dialog.server_added", name=name))
        self._load_profiles(update_ui=True)

    def _handle_subscription_added(self, name: str, url: str):
        """Handle a new subscription being added."""
        self._app_context.subscriptions.save(name, url)
        if self._toast:
            self._toast.success(t("add_dialog.subscription_added", name=name))
        self._load_profiles(update_ui=True)

    # --- Chain Management ---
    def _select_chain(self, chain: dict):
        """Handle chain selection for connection."""
        # Check if chain is valid
        if not chain.get("valid", True):
            if self._toast:
                self._toast.error(t("chain.toast.invalid_chain"))
            return

        self._selected_profile_id = chain["id"]

        # Pass chain to parent with a special marker and exit server's country info
        chain_with_marker = chain.copy()
        chain_with_marker["_is_chain"] = True

        # Get exit server (last in chain) for country/flag display
        if chain.get("items"):
            last_profile_id = chain["items"][-1]
            exit_profile = self._app_context.get_profile_by_id(last_profile_id)
            if exit_profile:
                chain_with_marker["country_code"] = exit_profile.get("country_code")
                chain_with_marker["country_name"] = exit_profile.get("country_name")

        if self._on_server_selected:
            self._on_server_selected(chain_with_marker)
        self._load_profiles(update_ui=True)

    def _edit_chain(self, chain: dict):
        """Open chain builder view for editing."""
        self.show_chain_builder(existing_chain=chain)

    def _delete_chain(self, chain_id: str):
        """Delete a chain."""
        self._app_context.chains.delete(chain_id)
        self._load_profiles(update_ui=True)
        if self._page:
            if self._toast:
                self._toast.success(t("chain.toast.deleted"))
            self._page.update()

    def _handle_chain_saved(self, name: str, profile_ids: list):
        """Handle a new chain being saved."""
        chain_id = self._app_context.save_chain(name, profile_ids)
        if chain_id:
            if self._toast:
                self._toast.success(t("chain.toast.created", name=name))
            self._load_profiles(update_ui=True)

    def _handle_chain_updated(self, chain_id: str, name: str, profile_ids: list):
        """Handle a chain being updated."""
        success = self._app_context.update_chain(
            chain_id,
            {
                "name": name,
                "items": profile_ids,
            },
        )
        if success:
            if self._toast:
                self._toast.success(t("chain.toast.updated"))
            self._load_profiles(update_ui=True)

    def show_chain_builder(self, existing_chain: Optional[dict] = None):
        """Show the chain builder page for creating/editing a chain."""
        if not self._navigate_to:
            logger.warning("No navigate_to callback available for chain builder")
            return

        # Close the server sheet first
        if self._close_sheet:
            self._close_sheet()

        logger.info("Opening chain builder page")

        def on_back(e=None):
            """Handle back navigation from chain builder."""
            logger.info("Navigating back from chain builder")
            if self._navigate_back:
                self._navigate_back()
            # Reload profiles after returning
            self._load_profiles(update_ui=True)

        def on_save(name: str, profile_ids: list):
            """Handle chain save."""
            if existing_chain:
                if self._toast:
                    self._toast.success(t("chain.toast.updated"))
            else:
                if self._toast:
                    self._toast.success(t("chain.toast.created", name=name))

        chain_page = ChainBuilderPage(
            app_context=self._app_context,
            on_back=on_back,
            on_save=on_save,
            existing_chain=existing_chain,
        )

        # Navigate to the chain builder page
        self._navigate_to(chain_page)
