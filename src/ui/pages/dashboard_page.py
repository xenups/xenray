"""Dashboard Page – connection centerpiece + traffic cards + ServerCard."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import t
from src.ui.components.dashboard.connection_button import ConnectionButton
from src.ui.components.dashboard.traffic_cards import TrafficCards
from src.ui.controllers.dashboard_controller import DashboardController, DashboardState
from src.ui.theme import AppColors


class DashboardPage(ft.Container):
    """Dashboard Page – connection centerpiece + traffic cards + ServerCard."""

    def __init__(
        self,
        on_toggle_click: Callable,
        on_change_server_click: Callable,
        on_open_statistics_click: Optional[Callable] = None,
        connection_button: Optional[ConnectionButton] = None,
        app_context=None,
        server_card=None,
    ):
        self._on_toggle_click = on_toggle_click
        self._on_change_server_click = on_change_server_click
        self._on_open_statistics_click = on_open_statistics_click
        self._app_context = app_context
        self._server_card_component = server_card

        self._is_connected = False
        self._is_online = True
        self._lan_sharing_enabled = False

        self._toggle_button = (
            connection_button if connection_button is not None else ConnectionButton(on_click=self._on_toggle_click)
        )

        self._center_status_text = self._toggle_button._status_text
        self._uptime_text = self._toggle_button._uptime_text

        self._controller = DashboardController(
            on_state_changed=self._on_controller_state_changed,
            on_uptime_updated=self.update_uptime,
            on_stats_updated=self._on_controller_stats_updated,
        )

        hero_center_section = ft.Container(
            content=self._toggle_button,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(vertical=8),
            expand=True,
        )

        self._traffic_cards = TrafficCards()
        self._dl_value_text = self._traffic_cards._dl_value_text
        self._ul_value_text = self._traffic_cards._ul_value_text

        if self._server_card_component:
            self._server_card_component.margin = None
            self._server_card_component.height = 106
            self._server_card_component.border_radius = 14
            self._server_card_component.border = None
            self._server_card_component.padding = ft.Padding.symmetric(horizontal=12, vertical=8)

            try:
                self._server_card_component._list_btn.visible = False
                self._server_card_component._content_row.vertical_alignment = ft.CrossAxisAlignment.CENTER
            except Exception:
                pass

            self._server_card_component.on_click = lambda e: (
                self._on_change_server_click(e) if self._on_change_server_click else None
            )

            server_card_wrapper = ft.Container(
                content=self._server_card_component,
                width=235,
                height=106,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            )
        else:
            server_card_wrapper = ft.Container(
                content=ft.Text(
                    t("server_list.no_server"),
                    size=12,
                    color=AppColors.ON_SURFACE_VARIANT,
                ),
                width=235,
                height=106,
                alignment=ft.Alignment.CENTER,
                border_radius=14,
                bgcolor=ft.Colors.with_opacity(0.035, ft.Colors.WHITE),
                border=None,
                on_click=lambda e: (self._on_change_server_click(e) if self._on_change_server_click else None),
                ink=True,
            )

        cards_grid_row = ft.Row(
            [self._traffic_cards, server_card_wrapper],
            spacing=14,
            height=106,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        cards_grid_container = ft.Container(
            content=cards_grid_row,
            alignment=ft.Alignment.CENTER,
            margin=ft.Margin.only(bottom=10),
        )

        canvas_layout = ft.Column(
            [hero_center_section, cards_grid_container],
            spacing=10,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

        super().__init__(
            content=canvas_layout,
            padding=14,
            expand=True,
            bgcolor=ft.Colors.TRANSPARENT,
        )

    def _on_controller_state_changed(self, state: DashboardState) -> None:
        """Handle state change notification from DashboardController."""
        self._is_connected = state == DashboardState.CONNECTED
        if state == DashboardState.CONNECTING:
            self.set_state_connecting()
        elif state == DashboardState.CONNECTED:
            self.set_state_connected()
        elif state == DashboardState.DISCONNECTING:
            self.set_state_disconnecting()
        else:
            self.set_state_disconnected()

    def _on_controller_stats_updated(self, upload_str: str, download_str: str) -> None:
        """Handle stats update from DashboardController."""
        self._traffic_cards.update_speeds(download_str, upload_str)

    def set_state_disconnected(self) -> None:
        """Update UI to disconnected state."""
        self._is_connected = False
        self._controller.set_state(DashboardState.DISCONNECTED)
        self._toggle_button.set_state_disconnected()
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def set_state_connecting(self) -> None:
        """Update UI to connecting state."""

        self._controller.set_state(DashboardState.CONNECTING)
        self._toggle_button.set_state_connecting()
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def set_state_connected(self) -> None:
        """Update UI to connected state."""
        self._is_connected = True
        self._controller.set_state(DashboardState.CONNECTED)
        self._toggle_button.set_state_connected()
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def set_state_disconnecting(self) -> None:
        """Update UI to disconnecting state."""
        self._controller.set_state(DashboardState.DISCONNECTING)
        self._toggle_button.set_state_disconnecting()
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def update_uptime(self, uptime_str: str) -> None:
        """Update uptime counter."""
        self._toggle_button.set_uptime(uptime_str)

    def update_network_stats(
        self,
        rate_str: str = "0.0 MB/s",
        upload_str: str = "0.0 MB",
        download_str: str = "0.0 MB",
        speed_text: Optional[str] = None,
        upload_total: Optional[str] = None,
        download_total: Optional[str] = None,
    ) -> None:
        """Update download and upload throughput text values."""
        self._controller.process_network_stats(
            rate_str=rate_str,
            upload_str=upload_str,
            download_str=download_str,
            speed_text=speed_text,
            upload_total=upload_total,
            download_total=download_total,
        )

    def update_internet_status(self, is_online: bool) -> None:
        """Update internet status indicator."""
        self._is_online = is_online
        self._toggle_button.set_online_status(is_online)

    def set_lan_sharing_state(self, enabled: bool) -> None:
        """Update LAN sharing status indicator."""
        self._lan_sharing_enabled = enabled


# Backward-compatibility alias
DashboardView = DashboardPage
