"""Navigation Service - manages view transitions, route switching, and subpage navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import flet as ft

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class NavigationService:
    """Service handling navigation route switching and subpage transitions."""

    def __init__(self, main_window: MainWindow) -> None:
        self._mw = main_window

    def _set_stats_visible(self, visible: bool) -> None:
        """Mark the statistics page as shown/hidden to pause telemetry rendering."""
        view = getattr(self._mw, "_stitch_statistics_view", None)
        if view is not None and hasattr(view, "set_visible"):
            view.set_visible(visible)

    def navigate_to(self, control: ft.Control) -> None:
        """Navigate to a new view — suppress background updates during swap."""
        self._mw._nav_locked = True
        self._mw._view_switcher.content = control
        try:
            self._mw._view_switcher.update()
        except RuntimeError:
            pass
        self._mw._nav_locked = False
        # Any subpage navigation hides the statistics page.
        self._set_stats_visible(False)

    def navigate_back(self, e: Optional[ft.ControlEvent] = None) -> None:
        """Return to settings view or active tab from subpages."""
        target_tab = (
            self._mw._active_tab
            if self._mw._active_tab in ("settings", "statistics", "servers", "logs", "sni_spoof")
            else "settings"
        )
        self.on_nav_tab_changed(target_tab, force=True)

    def on_nav_tab_changed(self, tab_id: str, force: bool = False) -> None:
        """Switch the main content view based on selected nav tab using targeted updates."""
        if self._mw._active_tab == tab_id and not force:
            return
        self._mw._active_tab = tab_id
        view_map = {
            "dashboard": self._mw._stitch_dashboard_view,
            "statistics": self._mw._stitch_statistics_view,
            "servers": self._mw._stitch_servers_view,
            "logs": self._mw._stitch_logs_view,
            "sni_spoof": getattr(self._mw, "_stitch_sni_spoof_page", None),
            "settings": self._mw._stitch_settings_view,
        }
        target = view_map.get(tab_id, self._mw._stitch_dashboard_view)
        if target is None:
            target = self._mw._stitch_dashboard_view

        self._mw._view_switcher.content = target
        if hasattr(self._mw, "_nav_sidebar") and self._mw._nav_sidebar:
            self._mw._nav_sidebar.set_active_tab(tab_id)

        try:
            self._mw._view_switcher.update()
        except RuntimeError:
            pass

        self._set_stats_visible(tab_id == "statistics")

        if hasattr(self._mw, "_nav_sidebar") and self._mw._nav_sidebar:
            try:
                self._mw._nav_sidebar._buttons_container.update()
            except RuntimeError:
                pass

        if hasattr(self._mw, "_log_viewer") and self._mw._log_viewer:
            drawer_open = (
                getattr(self._mw._logs_drawer_component, "open", False)
                if hasattr(self._mw, "_logs_drawer_component") and self._mw._logs_drawer_component
                else False
            )
            self._mw._log_viewer.set_visible(tab_id == "logs" or drawer_open)

    def on_server_search(self, query: str) -> None:
        """Handle server search in ServersView."""
        if self._mw._profile_manager and self._mw._server_list:
            self._mw._server_list._load_profiles(search_query=query, update_ui=True)

    def open_add_server_dialog(self, e: Optional[ft.ControlEvent] = None) -> None:
        """Open the Add Server modal as a custom in-page Stack overlay.

        Delegates to the server list's own ``AddServerModalContainer`` (Layer 1
        of the server list Stack). Opening/closing only toggles that container's
        ``visible`` — ``page._dialogs`` and the background server list are never
        touched, so there is zero flicker and card animations never reset.
        """
        if self._mw._server_list:
            self._mw._server_list.open_add_dialog()

    def add_server_profile(self, name: str, config: dict) -> None:
        """Save a newly added server profile and refresh server list."""
        from src.services.connection.server_inspector import server_inspector

        pid = self._mw._app_context.profiles.save(name, config)
        if pid:
            profile = self._mw._app_context.profiles.get_by_id(pid) or {
                "id": pid,
                "name": name,
                "config": config,
            }
            # Auto-ping + location detection for the imported server (background).
            server_inspector.inspect({"id": pid, "name": name, "config": config})
            if self._mw._server_list and hasattr(self._mw._server_list, "append_server_item"):
                self._mw._server_list.append_server_item(profile)
            elif self._mw._server_list:
                self._mw._server_list._load_profiles(update_ui=True)
        elif self._mw._server_list:
            self._mw._server_list._load_profiles(update_ui=True)

    def add_subscription(self, name: str, url: str) -> None:
        """Save a newly added subscription, fetch its servers, and refresh."""
        from src.core.subscription_manager import SubscriptionManager

        sub_id = self._mw._app_context.subscriptions.save(name, url)
        if sub_id:
            # Fetch + parse immediately so the imported servers get inspected in
            # the background (the update flow publishes server_inspected events).
            SubscriptionManager(self._mw._app_context).update_subscription(sub_id, callback=None)
        if self._mw._server_list:
            self._mw._server_list._load_profiles(update_ui=True)

    def open_routing_page(self) -> None:
        """Navigate to routing page."""
        from src.ui.pages.routing_page import RoutingPage

        page = RoutingPage(
            app_context=self._mw._app_context,
            on_back=self.navigate_back,
        )
        self.navigate_to(page)

    def open_dns_page(self) -> None:
        """Navigate to DNS management page."""
        from src.ui.pages.dns_page import DNSPage

        page = DNSPage(
            app_context=self._mw._app_context,
            on_back=self.navigate_back,
        )
        self.navigate_to(page)

    def open_lan_page(self) -> None:
        """Navigate to the dedicated LAN Sharing view (cached singleton)."""
        from src.ui.pages.lan_sharing_page import LanSharingView

        self._mw._active_tab = "lan"
        if hasattr(self._mw, "_nav_sidebar") and self._mw._nav_sidebar:
            self._mw._nav_sidebar.set_active_tab("lan")

        view = getattr(self._mw, "_lan_sharing_view", None)
        if view is None:
            view = LanSharingView(
                app_context=self._mw._app_context,
                on_back=self.navigate_back,
                on_lan_toggle=lambda enabled: (
                    self._mw._nav_sidebar.update_lan_button(enabled)
                    if hasattr(self._mw, "_nav_sidebar") and self._mw._nav_sidebar
                    else None
                ),
            )
            self._mw._lan_sharing_view = view
        self.navigate_to(view)
