"""Profile Selection Handler - manages profile UI state updates across Stitch views."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from src.services.core_engines.config_utils import is_ip
from src.ui.helpers.profile_presenter import ProfilePresenter

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class ProfileSelectionHandler:
    """Handler managing profile UI synchronization and server selection events."""

    def __init__(self, main_window: MainWindow) -> None:
        self._mw = main_window

    def update_selected_profile_ui(self, profile: dict) -> None:
        """Updates all Stitch views and server cards with selected profile attributes."""
        self._mw._selected_profile = profile
        if self._mw._server_card:
            self._mw._server_card.update_server(profile)

        info: dict = {}
        try:
            info = ProfilePresenter.extract_profile_info(profile)
            self._apply_profile_info(profile, info)
        except Exception:
            pass

        # Defer a potentially slow domain -> IP lookup to a background thread so
        # the Flet event loop is never blocked; refresh the display when it lands.
        self._schedule_server_ip_resolution(profile, info)

        if self._mw._server_sheet:
            try:
                if self._mw._server_sheet.open:
                    self._mw._server_sheet.open = False
                    self._mw._server_sheet.update()
            except Exception:
                pass
        try:
            if self._mw._server_card and self._mw._server_card.page:
                self._mw._server_card.update()
        except Exception:
            pass

    def _apply_profile_info(self, profile: dict, info: dict) -> None:
        """Push extracted profile info to all Stitch views (no blocking I/O)."""
        name = profile.get("name", "") or profile.get("remark", "")
        latency = info.get("latency", "--")
        country_code = info.get("country_code", "")
        country_name = info.get("country_name", "")
        protocol = info.get("protocol", "")
        encryption = info.get("encryption", "")
        server_ip = info.get("server_ip", "")

        if hasattr(self._mw, "_stitch_dashboard_view") and self._mw._stitch_dashboard_view:
            self._mw._stitch_dashboard_view.update_server_info(
                name=name,
                latency=latency,
                protocol=protocol,
                encryption=encryption,
                server_ip=server_ip,
                country_code=country_code,
                country_name=country_name,
            )

        if hasattr(self._mw, "_stitch_servers_view") and self._mw._stitch_servers_view:
            self._mw._stitch_servers_view.update_hero_node(
                name=name,
                latency=latency,
                protocol=protocol,
                country_code=country_code,
            )

        if hasattr(self._mw, "_stitch_statistics_view") and self._mw._stitch_statistics_view:
            self._mw._stitch_statistics_view.update_server_info(
                name=name,
                country_code=country_code,
                server_ip=server_ip,
            )

    def _schedule_server_ip_resolution(self, profile: dict, info: dict) -> None:
        """Resolve an uncached domain server address to its IP off the event loop.

        ``info["server_ip"]`` holds the raw address for uncached domains (the
        non-blocking presenter returns it as-is). Only then is a background DNS
        lookup scheduled; on success the cached value is re-applied to the views.
        """
        server_ip = info.get("server_ip", "")
        if not server_ip or server_ip == "--" or is_ip(server_ip):
            return  # already an IP (or nothing to resolve)

        raw_addr = server_ip

        def _work():
            resolved = ProfilePresenter.resolve_server_ip_blocking(raw_addr)
            if resolved and resolved != raw_addr and self._mw._ui_helper:
                self._mw._ui_helper.call(lambda: self._refresh_server_ip())

        threading.Thread(target=_work, daemon=True).start()

    def _refresh_server_ip(self) -> None:
        """Re-apply profile info (now served from the populated DNS cache)."""
        profile = self._mw._selected_profile
        if not profile:
            return
        try:
            info = ProfilePresenter.extract_profile_info(profile)
            self._apply_profile_info(profile, info)
        except Exception:
            pass

        if self._mw._server_sheet:
            try:
                if self._mw._server_sheet.open:
                    self._mw._server_sheet.open = False
                    self._mw._server_sheet.update()
            except Exception:
                pass
        try:
            if self._mw._server_card and self._mw._server_card.page:
                self._mw._server_card.update()
        except Exception:
            pass

    def on_server_selected(self, profile: dict) -> None:
        """Handle server item selection from server list or bottom sheet."""
        self._mw._ui_helper.call(lambda: self.update_selected_profile_ui(profile))

        try:
            self._mw._app_context.settings.set_last_selected_profile_id(profile.get("id"))
        except Exception:
            pass

        if not self._mw._is_running and not self._mw._connecting:
            self._mw._ui_helper.call(self._mw._status_display.set_pre_connection_ping, "...", False)
            self._mw._latency_monitor_handler.trigger_single_check()

        if self._mw._is_running:
            self._mw._trigger_reconnect()

        self._mw._on_nav_tab_changed("dashboard")
