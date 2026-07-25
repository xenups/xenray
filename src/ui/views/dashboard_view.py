"""Dashboard View Component matching Slate Dark & Deep Apple Purple design specs."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.components.connection_button import ConnectionButton
from src.ui.components.dashboard.node_card_component import NodeCardComponent
from src.ui.components.dashboard.traffic_chart_component import TrafficChartComponent
from src.ui.theme import AppColors


class DashboardView(ft.Container):
    """Main Dashboard view matching Slate Dark & Deep Apple Purple specs."""

    def __init__(
        self,
        on_toggle_click: Callable,
        on_change_server_click: Callable,
        connection_button: ConnectionButton | None = None,
    ):
        self._on_toggle_click = on_toggle_click
        self._on_change_server_click = on_change_server_click

        WHITE = ft.Colors.WHITE
        MUTED_WHITE = AppColors.ON_SURFACE_VARIANT
        PURPLE = AppColors.PRIMARY

        self._is_connected = False
        self._is_online = True

        # Status Dot & Text
        self._status_dot = ft.Container(
            width=8,
            height=8,
            border_radius=4,
            bgcolor=ft.Colors.GREEN_400,
        )

        self._top_status_text = ft.Text(
            t("dashboard.system_ready", default="SYSTEM READY"),
            size=12,
            weight=ft.FontWeight.W_700,
            color=WHITE,
        )

        self._status_indicator_row = ft.Row(
            [
                self._status_dot,
                self._top_status_text,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._center_status_text = ft.Text(
            t("dashboard.disconnected", default="Disconnected"),
            size=14,
            weight=ft.FontWeight.W_700,
            color=WHITE,
        )
        self._uptime_text = ft.Text(
            "00:00:00",
            size=11,
            color=MUTED_WHITE,
        )

        # Signal bars indicator
        self._signal_bars = []
        self._signal_row = ft.Row(
            spacing=3,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.END,
            height=16,
        )
        for i in range(5):
            bar = ft.Container(
                width=3,
                height=4 + i * 3,
                bgcolor=ft.Colors.with_opacity(0.35 + i * 0.1, MUTED_WHITE),
                border_radius=2,
                animate=ft.Animation(400, ft.AnimationCurve.EASE_OUT),
            )
            self._signal_bars.append(bar)
            self._signal_row.controls.append(bar)

        self._toggle_button = connection_button if connection_button is not None else ConnectionButton(on_click=self._on_toggle_click)

        # Modular Subcomponents
        self._traffic_card = TrafficChartComponent()
        self._node_card = NodeCardComponent(on_change_server_click=self._on_change_server_click)

        # Layout Assembly
        centerpiece = ft.Column(
            [
                self._toggle_button,
                ft.Column(
                    [
                        self._center_status_text,
                        self._uptime_text,
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
        )

        top_bar = ft.Row(
            [
                self._status_indicator_row,
                self._signal_row,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        bento_row = ft.Row(
            [
                self._traffic_card.view,
                self._node_card.view,
            ],
            spacing=14,
            expand=True,
        )

        content_layout = ft.Column(
            [
                top_bar,
                ft.Container(content=centerpiece, expand=True, alignment=ft.Alignment.CENTER),
                bento_row,
            ],
            spacing=10,
            expand=True,
        )

        super().__init__(
            content=content_layout,
            padding=16,
            expand=True,
        )

    def set_connection_state(self, is_connected: bool, is_connecting: bool = False, is_disconnecting: bool = False):
        """Update centerpiece status, button animation state, and signal bars."""
        self._is_connected = is_connected

        if is_disconnecting:
            self._status_dot.bgcolor = ft.Colors.RED_400
            self._top_status_text.value = t("dashboard.disconnecting", default="DISCONNECTING...")
            self._center_status_text.value = t("status.disconnecting", default="Disconnecting...")
            self._toggle_button.set_disconnecting()
            self._animate_signal_bars(is_active=True, is_connecting=False, is_disconnecting=True)
        elif is_connecting:
            self._status_dot.bgcolor = ft.Colors.AMBER_400
            self._top_status_text.value = t("dashboard.connecting", default="CONNECTING...")
            self._center_status_text.value = t("status.connecting", default="Connecting...")
            self._toggle_button.set_connecting()
            self._animate_signal_bars(is_active=True, is_connecting=True)
        elif is_connected:
            self._status_dot.bgcolor = ft.Colors.GREEN_400
            self._top_status_text.value = t("dashboard.protected", default="PROTECTED")
            self._center_status_text.value = t("dashboard.connected", default="Connected")
            self._toggle_button.set_connected()
            self._animate_signal_bars(is_active=True, is_connecting=False)
        else:
            self._status_dot.bgcolor = ft.Colors.GREY_500 if not self._is_online else ft.Colors.GREEN_400
            self._top_status_text.value = t("dashboard.system_ready", default="SYSTEM READY")
            self._center_status_text.value = t("dashboard.disconnected", default="Disconnected")
            self._uptime_text.value = "00:00:00"
            self._toggle_button.set_disconnected()
            self._animate_signal_bars(is_active=False, is_connecting=False)

        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def set_step(self, step_text: str):
        """Update real-time intermediate status step under main connection button."""
        if hasattr(self, "_center_status_text") and self._center_status_text and step_text:
            self._center_status_text.value = step_text
            try:
                if self._center_status_text.page:
                    self._center_status_text.update()
            except Exception:
                pass

    def update_network_stats(
        self,
        rate_str: str = "0.0 MB/s",
        upload_str: str = "0.0 MB",
        download_str: str = "0.0 MB",
        download_bps: float = 0.0,
        upload_bps: float = 0.0,
        total_bps: float = 0.0,
        speed_text: str | None = None,
        upload_total: str | None = None,
        download_total: str | None = None,
    ):
        """Delegate to TrafficChartComponent and refresh container state."""
        self._traffic_card.update_network_stats(
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
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def update_glow_intensity(self, total_bps: float = 0.0):
        """Update background glow intensity based on total network throughput."""
        pass

    def update_server_info(
        self,
        name: str = "",
        latency: str = "",
        protocol: str = "",
        encryption: str = "",
        server_ip: str = "",
        country_code: str = "",
        country_name: str = "",
        local_ip: str | None = None,
        **kwargs,
    ):
        """Delegate to NodeCardComponent."""
        self._node_card.update_server_info(
            name=name,
            latency=latency,
            protocol=protocol,
            encryption=encryption,
            server_ip=server_ip,
            country_code=country_code,
            country_name=country_name,
            local_ip=local_ip,
            **kwargs,
        )

    def update_internet_status(self, is_online: bool):
        """Update internet connection status indicator."""
        self._is_online = is_online
        try:
            if not is_online and not self._is_connected:
                self._status_dot.bgcolor = ft.Colors.RED_400
                self._top_status_text.value = t("dashboard.no_internet", default="NO INTERNET")
                if self.page:
                    self._status_indicator_row.update()
            elif is_online and not self._is_connected and self._top_status_text.value == t("dashboard.no_internet", default="NO INTERNET"):
                self._status_dot.bgcolor = ft.Colors.GREEN_400
                self._top_status_text.value = t("dashboard.system_ready", default="SYSTEM READY")
                if self.page:
                    self._status_indicator_row.update()
        except Exception:
            pass

    def update_uptime(self, uptime_str: str):
        """Update session duration counter text."""
        self._uptime_text.value = uptime_str
        try:
            if hasattr(self, "_uptime_text") and self._uptime_text.page:
                self._uptime_text.update()
        except Exception:
            pass

    def _animate_signal_bars(self, is_active: bool, is_connecting: bool, is_disconnecting: bool = False):
        MUTED_WHITE = AppColors.ON_SURFACE_VARIANT
        PURPLE = AppColors.PRIMARY
        active_heights = [4, 7.5, 11.0, 14.5, 3] if is_active else [3, 3, 3, 3, 3]

        for i, bar in enumerate(self._signal_bars):
            bar.height = active_heights[i]
            if is_disconnecting:
                bar.bgcolor = ft.Colors.with_opacity(0.7, ft.Colors.RED_400)
            elif is_connecting:
                bar.bgcolor = ft.Colors.with_opacity(0.6, PURPLE)
            elif is_active:
                bar.bgcolor = ft.Colors.with_opacity(0.85, MUTED_WHITE)
            else:
                bar.bgcolor = ft.Colors.with_opacity(0.25, MUTED_WHITE)

        try:
            if self._signal_row.page:
                self._signal_row.update()
        except Exception:
            pass
