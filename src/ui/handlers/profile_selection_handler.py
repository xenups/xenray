"""Profile Selection Handler - manages profile UI state updates across Stitch views."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

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

        try:
            info = ProfilePresenter.extract_profile_info(profile)
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
