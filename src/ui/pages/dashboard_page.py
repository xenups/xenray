"""Dashboard Page – connection centerpiece + traffic cards + ServerCard."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.event_bus import (
    TOPIC_ACTIVE_SERVER_PING_UPDATED,
    TOPIC_CONNECTION_STATE_CHANGED,
    TOPIC_TELEMETRY_UPDATED,
    event_bus,
)
from src.core.i18n import t
from src.ui.components.dashboard.connection_button import ConnectionButton
from src.ui.components.dashboard.traffic_cards import TrafficCards
from src.ui.controllers.dashboard_controller import DashboardController, DashboardState
from src.ui.helpers.status_helper import get_short_status_label
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
        self._is_connecting = False
        self._is_disconnecting = False
        self._is_online = True
        self._lan_sharing_enabled = False

        self._toggle_button = (
            connection_button if connection_button is not None else ConnectionButton(on_click=self._on_toggle_click)
        )

        self._controller = DashboardController(
            on_state_changed=self._on_controller_state_changed,
            on_uptime_updated=self.update_uptime,
            on_stats_updated=self._on_controller_stats_updated,
        )

        event_bus.subscribe(TOPIC_TELEMETRY_UPDATED, self._on_telemetry_event)
        event_bus.subscribe(TOPIC_CONNECTION_STATE_CHANGED, self._on_connection_state_event)
        event_bus.subscribe(TOPIC_ACTIVE_SERVER_PING_UPDATED, self._on_active_server_ping_updated)

        hero_center_section = ft.Container(
            content=self._toggle_button,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(vertical=8),
            expand=True,
        )

        self._traffic_cards = TrafficCards(on_card_click=self._on_open_statistics_click)

        if self._server_card_component:
            self._server_card_component.margin = None
            self._server_card_component.height = 124
            self._server_card_component.border_radius = 14
            self._server_card_component.border = None
            self._server_card_component.padding = ft.Padding.symmetric(horizontal=12, vertical=8)
            self._server_card_component.alignment = ft.Alignment.CENTER

            try:
                self._server_card_component._list_btn.visible = False
                if hasattr(self._server_card_component, "_text_column"):
                    self._server_card_component._text_column.expand = False
                self._server_card_component._content_row.vertical_alignment = ft.CrossAxisAlignment.CENTER
                self._server_card_component._content_row.alignment = ft.MainAxisAlignment.CENTER
            except Exception:
                pass

            self._server_card_component.on_click = lambda e: (
                self._on_change_server_click(e) if self._on_change_server_click else None
            )

            server_card_wrapper = ft.Container(
                content=self._server_card_component,
                width=235,
                height=124,
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
                height=124,
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
            height=124,
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

    def dispose(self) -> None:
        """Release EventBus subscriptions held by this view."""
        event_bus.unsubscribe(TOPIC_TELEMETRY_UPDATED, self._on_telemetry_event)
        event_bus.unsubscribe(TOPIC_CONNECTION_STATE_CHANGED, self._on_connection_state_event)
        event_bus.unsubscribe(TOPIC_ACTIVE_SERVER_PING_UPDATED, self._on_active_server_ping_updated)

    def _on_controller_state_changed(self, state: DashboardState, label: str) -> None:
        """Handle state change notification from DashboardController."""
        self._is_connected = state == DashboardState.CONNECTED
        self._is_connecting = state == DashboardState.CONNECTING
        self._is_disconnecting = state == DashboardState.DISCONNECTING

        if state == DashboardState.CONNECTING:
            self._toggle_button.set_connecting(label)
        elif state == DashboardState.CONNECTED:
            self._toggle_button.set_connected(label)
        elif state == DashboardState.DISCONNECTING:
            self._toggle_button.set_disconnecting(label)
        else:
            self._toggle_button.set_disconnected(label)

    def _on_controller_stats_updated(self, dl_text: str, ul_text: str, total_bps: float) -> None:
        """Handle stats update from DashboardController."""
        self._traffic_cards.update_speeds(dl_text, ul_text)
        self._toggle_button.update_network_activity(total_bps)

    def _on_telemetry_event(self, data) -> None:
        """Handle telemetry_updated EventBus events (published on the UI event loop)."""
        if not isinstance(data, dict):
            return
        try:
            self.update_network_stats(
                rate_str=data.get("rate_str", "0.0 MB/s"),
                download_bps=float(data.get("download_bps", 0.0)),
                upload_bps=float(data.get("upload_bps", 0.0)),
                total_bps=float(data.get("total_bps", 0.0)),
            )
        except Exception:
            pass

    def _on_active_server_ping_updated(self, data) -> None:
        """Handle active_server_ping_updated events and render latency live."""
        if not isinstance(data, dict):
            return
        # Only meaningful while disconnected — once connected the status text is
        # driven by the connection state machine.
        if self._is_connected or self._is_connecting or self._is_disconnecting:
            return
        result_str = data.get("result_str")
        if not result_str:
            return
        try:
            self._toggle_button.set_pre_connection_ping(result_str, bool(data.get("success", False)))
        except Exception:
            pass

    def _on_connection_state_event(self, data) -> None:
        """Handle connection_state_changed EventBus events in real time."""
        if not isinstance(data, dict):
            return
        try:
            evt = data.get("event")
            payload = data.get("data") or {}
            connected_at = payload.get("connected_at")
            if evt == "connected":
                self.set_connection_state(is_connected=True, connected_at=connected_at)
            elif evt == "connecting":
                self.set_connection_state(is_connected=False, is_connecting=True)
            elif evt == "disconnecting":
                self.set_connection_state(is_connected=False, is_disconnecting=True)
            elif evt in ("disconnected", "connect_failed"):
                self.set_connection_state(is_connected=False)
        except Exception:
            pass

    def set_connection_state(
        self,
        is_connected: bool,
        is_connecting: bool = False,
        is_disconnecting: bool = False,
        connected_at: Optional[float] = None,
    ) -> None:
        """Update dashboard connection state (mirrors the legacy DashboardView API)."""
        self._is_connected = is_connected
        self._is_connecting = is_connecting
        self._is_disconnecting = is_disconnecting
        self._controller.set_connection_state(
            is_connected=is_connected,
            is_connecting=is_connecting,
            is_disconnecting=is_disconnecting,
            connected_at=connected_at,
        )

    def set_step(self, step_text: str) -> None:
        """Update the center status text during connection step transitions."""
        if not step_text:
            return
        self._toggle_button.set_step(get_short_status_label(step_text))

    def set_pre_connection_ping(self, latency_text: str, is_success: bool = True) -> None:
        """Update active server ping on controller and connection button when disconnected."""
        label = self._controller.update_ping(latency_text, is_success)
        if label and not self._is_connected and not self._is_connecting and not self._is_disconnecting:
            self._toggle_button.set_disconnected(label)

    def set_state_disconnected(self) -> None:
        """Update UI to disconnected state."""
        self.set_connection_state(is_connected=False)

    def set_state_connecting(self) -> None:
        """Update UI to connecting state."""
        self.set_connection_state(is_connected=False, is_connecting=True)

    def set_state_connected(self) -> None:
        """Update UI to connected state."""
        self.set_connection_state(is_connected=True)

    def set_state_disconnecting(self) -> None:
        """Update UI to disconnecting state."""
        self.set_connection_state(is_connected=False, is_disconnecting=True)

    def update_uptime(self, elapsed: int | str) -> None:
        """Update uptime counter."""
        self._toggle_button.update_uptime(elapsed)

    def update_glow_intensity(self, total_bps: float = 0.0) -> None:
        """Update live throughput glow on the connection button."""
        self._toggle_button.update_network_activity(total_bps)

    def update_network_stats(
        self,
        rate_str: str = "0.0 MB/s",
        upload_str: str = "0.0 MB",
        download_str: str = "0.0 MB",
        download_bps: float = 0.0,
        upload_bps: float = 0.0,
        total_bps: float = 0.0,
        speed_text: Optional[str] = None,
        upload_total: Optional[str] = None,
        download_total: Optional[str] = None,
    ) -> None:
        """Update download and upload throughput text values."""
        self._controller.process_network_stats(
            rate_str=rate_str,
            upload_str=upload_str,
            download_str=download_str,
            download_bps=download_bps,
            upload_bps=upload_bps,
            total_bps=total_bps,
            speed_text=speed_text,
            upload_total=upload_total,
            download_total=download_total,
        )

    def update_internet_status(self, is_online: bool) -> None:
        """Update internet status indicator."""
        self._is_online = is_online
        self._toggle_button.set_online_status(is_online)

    def update_server_info(self, *args, **kwargs) -> None:
        """No-op: ServerCard updates itself via main_window's profile update flow."""

    def update_lan_sharing(self, is_enabled: bool, ip_address: str = "") -> None:
        """Update LAN sharing status indicator."""
        self._lan_sharing_enabled = is_enabled

    def set_lan_sharing_state(self, enabled: bool) -> None:
        """Update LAN sharing status indicator."""
        self._lan_sharing_enabled = enabled


# Backward-compatibility alias
DashboardView = DashboardPage
