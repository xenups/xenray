"""Thread-safe Server List component for XenRay."""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import flet as ft

from src.core.config_manager import ConfigManager
from src.core.i18n import t
from src.core.logger import logger
from src.core.subscription_manager import SubscriptionManager
from src.services.latency_tester import LatencyTester
from src.ui.components.add_server_dialog import AddServerDialog
from src.ui.components.server_list_header import ServerListHeader
from src.ui.components.server_list_item import ServerListItem
from src.ui.components.subscription_list_item import SubscriptionListItem


class ServerList(ft.Container):
    """Thread-safe Server List component for XenRay."""

    def __init__(
        self,
        config_manager: ConfigManager,
        on_server_selected: Callable,
        on_profile_updated: Callable = None,
    ):
        self._config_manager = config_manager
        self._subscription_manager = SubscriptionManager(config_manager)
        self._on_server_selected = on_server_selected
        self._on_profile_updated = on_profile_updated

        # Data
        self._profiles: list[dict] = []
        self._subscriptions: list[dict] = []

        # State
        self._page: Optional[ft.Page] = None
        self._current_list_view = None
        self._selected_profile_id = None
        self._active_subscription = None

        # Item tracking for updates
        self._item_map: dict[str, ServerListItem] = {}

        # Latency Tester
        self._latency_tester = LatencyTester(
            on_test_start=self._on_latency_test_start,
            on_test_complete=self._on_latency_test_complete,
            on_all_complete=self._on_all_latency_tests_complete,
        )

        # Header Component
        self._header = ServerListHeader(
            get_sort_mode=self._config_manager.get_sort_mode,
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
        )

        # Animated Body Switcher
        self._body_switcher = ft.AnimatedSwitcher(
            content=ft.Container(),
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=150,
            reverse_duration=150,
            switch_in_curve=ft.AnimationCurve.EASE_IN,
            switch_out_curve=ft.AnimationCurve.EASE_OUT,
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
            bgcolor=ft.Colors.TRANSPARENT,
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
        self._config_manager.set_sort_mode(mode)
        if self._active_subscription:
            self._enter_subscription_view(
                self._active_subscription, preserve_tests=True
            )
        else:
            self._load_profiles(update_ui=True)

    def _apply_sort(self, items: list) -> list:
        """Apply current sort mode to items."""
        mode = self._config_manager.get_sort_mode()

        def get_latency(item):
            pid = item.get("id")
            cached = self._latency_tester.get_cached_result(pid)
            if cached:
                return cached[2]  # latency_val
            return 999999

        if mode == "name_asc":
            return sorted(items, key=lambda x: x.get("name", "").lower())
        if mode == "ping_asc":
            return sorted(items, key=get_latency)
        return items

    # --- Profile Loading ---
    def _load_profiles(self, update_ui=False):
        """Load and display profiles."""

        def _task():
            self._profiles = self._config_manager.load_profiles()
            self._subscriptions = self._config_manager.load_subscriptions()
            self._subscriptions.sort(key=lambda x: x.get("name", "").lower())

            # If in subscription view, refresh that instead
            if self._active_subscription:
                fresh_sub = next(
                    (
                        s
                        for s in self._subscriptions
                        if s["id"] == self._active_subscription["id"]
                    ),
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

            # Add subscriptions
            for sub in self._subscriptions:
                new_list_view.controls.append(
                    SubscriptionListItem(sub, self._enter_subscription_view)
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
            if self._page:
                self._page.open(
                    ft.SnackBar(content=ft.Text(t("server_list.test_in_progress")))
                )
                self._page.update()
            return

        profiles = []
        for profile_id, item in self._item_map.items():
            profiles.append(item._profile)

        if not profiles:
            return

        if self._page:
            self._page.open(ft.SnackBar(content=ft.Text(t("server_list.test_started"))))
            self._page.update()

        self._latency_tester.test_profiles(profiles)

    def _on_latency_test_start(self, profile: dict):
        """Called when a latency test starts for a profile."""
        item = self._item_map.get(profile.get("id"))
        if item:
            self._ui(
                lambda: item.update_ping(t("server_list.testing"), ft.Colors.BLUE_400)
            )

    def _on_latency_test_complete(
        self, profile: dict, success: bool, result: str, country_data: Optional[dict]
    ):
        """Called when a latency test completes for a profile."""
        pid = profile.get("id")
        item = self._item_map.get(pid)

        # Update country data if received
        if success and country_data:
            profile.update(country_data)
            if self._active_subscription:
                self._config_manager.save_subscription_data(self._active_subscription)
            else:
                self._config_manager.update_profile(pid, country_data)

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
                "last_latency_val": self._latency_tester.get_cached_result(pid)[2]
                if success
                else None,
            }
            if self._active_subscription:
                self._config_manager.save_subscription_data(self._active_subscription)
            else:
                self._config_manager.update_profile(pid, latency_data)

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
        self._config_manager.delete_profile(profile_id)
        self._load_profiles(update_ui=True)
        if self._page:
            self._page.open(
                ft.SnackBar(content=ft.Text(t("server_list.server_deleted")))
            )
            self._page.update()

    # --- Subscription Actions ---
    def _update_subscription(self, sub_id: str):
        """Update a subscription."""
        if not self._page:
            return
        self._page.open(
            ft.SnackBar(content=ft.Text(t("server_list.updating_subscription")))
        )
        self._page.update()

        def callback(success, msg):
            def _ui_update():
                if success:
                    self._page.open(
                        ft.SnackBar(content=ft.Text(msg, color=ft.Colors.GREEN_400))
                    )
                    self._load_profiles(update_ui=True)
                else:
                    self._page.open(
                        ft.SnackBar(
                            content=ft.Text(
                                t("server_list.update_failed", msg=msg),
                                color=ft.Colors.RED_400,
                            )
                        )
                    )
                self._page.update()

            self._ui(_ui_update)

        self._subscription_manager.update_subscription(sub_id, callback)

    def _delete_subscription(self, sub_id: str):
        """Delete a subscription."""
        self._config_manager.delete_subscription(sub_id)
        self._load_profiles(update_ui=True)
        if self._page:
            self._page.open(
                ft.SnackBar(content=ft.Text(t("server_list.subscription_deleted")))
            )
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
        self._config_manager.save_profile(name, config)
        if self._page:
            self._page.open(
                ft.SnackBar(
                    content=ft.Text(
                        t("add_dialog.server_added", name=name),
                        color=ft.Colors.GREEN_400,
                    )
                )
            )
        self._load_profiles(update_ui=True)

    def _handle_subscription_added(self, name: str, url: str):
        """Handle a new subscription being added."""
        self._config_manager.save_subscription(name, url)
        if self._page:
            self._page.open(
                ft.SnackBar(
                    content=ft.Text(
                        t("add_dialog.subscription_added", name=name),
                        color=ft.Colors.GREEN_400,
                    )
                )
            )
        self._load_profiles(update_ui=True)
