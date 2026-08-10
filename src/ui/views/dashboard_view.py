from __future__ import annotations

import threading
import time
from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.components.connection_button import ConnectionButton
from src.ui.theme import AppColors
from src.utils.network_interface import NetworkInterfaceDetector


class DashboardView(ft.Container):
    """Dashboard View – connection centerpiece + traffic cards + ServerCard."""

    def __init__(
        self,
        on_toggle_click: Callable,
        on_change_server_click: Callable,
        on_open_statistics_click: Callable | None = None,
        connection_button: ConnectionButton | None = None,
        app_context=None,
        server_card=None,
    ):
        self._on_toggle_click = on_toggle_click
        self._on_change_server_click = on_change_server_click
        self._on_open_statistics_click = on_open_statistics_click
        self._app_context = app_context
        self._server_card_component = server_card  # The shared ServerCard instance

        WHITE = ft.Colors.WHITE
        BLACK = ft.Colors.BLACK
        MUTED_WHITE = AppColors.ON_SURFACE_VARIANT

        self._is_connected = False
        self._is_online = True
        self._timer_running = False
        self._start_time = 0.0
        self._timer_thread: threading.Thread | None = None
        self._lan_sharing_enabled = False

        # --- 1. Center Connection Core (Hero Section) ---
        self._toggle_button = (
            connection_button if connection_button is not None else ConnectionButton(on_click=self._on_toggle_click)
        )

        self._center_status_text = self._toggle_button._status_text
        self._uptime_text = self._toggle_button._uptime_text

        hero_center_section = ft.Container(
            content=self._toggle_button,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(vertical=8),
            expand=True,
        )

        # --- 2. Bottom Cards Section (Download/Upload Left + 4-Row Server Card Right) ---
        GLASS_BG = ft.Colors.with_opacity(0.04, WHITE)
        GLASS_BORDER = ft.Border.all(1.0, ft.Colors.with_opacity(0.1, WHITE))
        GLASS_SHADOW = ft.BoxShadow(
            spread_radius=0,
            blur_radius=16,
            color=ft.Colors.with_opacity(0.25, BLACK),
            offset=ft.Offset(0, 4),
        )
        GLASS_BLUR = ft.Blur(12, 12)

        self._dl_value_text = ft.Text("0.0 MB/s", size=13, weight=ft.FontWeight.W_700, color=WHITE)
        self._ul_value_text = ft.Text("0.0 MB/s", size=13, weight=ft.FontWeight.W_700, color=WHITE)

        # Left Column: Top Download Card (Compact 185px width)
        download_card = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(
                            ft.Icons.SOUTH_WEST_ROUNDED,
                            size=16,
                            color="#38bdf8",
                        ),
                        width=30,
                        height=30,
                        border_radius=8,
                        bgcolor=ft.Colors.with_opacity(0.14, "#38bdf8"),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                "Download",
                                size=10,
                                color=MUTED_WHITE,
                                weight=ft.FontWeight.W_500,
                            ),
                            self._dl_value_text,
                        ],
                        spacing=1,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=185,
            height=49,
            padding=ft.Padding.symmetric(vertical=6, horizontal=10),
            border_radius=14,
            bgcolor=ft.Colors.with_opacity(0.035, ft.Colors.WHITE),
            border=None,
        )

        # Left Column: Bottom Upload Card (Compact 185px width)
        upload_card = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(
                            ft.Icons.NORTH_EAST_ROUNDED,
                            size=16,
                            color="#c084fc",
                        ),
                        width=30,
                        height=30,
                        border_radius=8,
                        bgcolor=ft.Colors.with_opacity(0.14, "#c084fc"),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                "Upload",
                                size=10,
                                color=MUTED_WHITE,
                                weight=ft.FontWeight.W_500,
                            ),
                            self._ul_value_text,
                        ],
                        spacing=1,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=185,
            height=49,
            padding=ft.Padding.symmetric(vertical=6, horizontal=10),
            border_radius=14,
            bgcolor=ft.Colors.with_opacity(0.035, ft.Colors.WHITE),
            border=None,
        )

        left_traffic_column = ft.Column(
            [
                download_card,
                upload_card,
            ],
            width=185,
            spacing=8,
            height=106,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # --- 2b. Right column: ServerCard (shared instance, sized to match previous card) ---
        if self._server_card_component:
            # Strip the card's built-in large margin so it fits the compact row
            self._server_card_component.margin = None
            self._server_card_component.height = 106
            self._server_card_component.border_radius = 14
            self._server_card_component.border = None

            # Compact padding so text fits cleanly in the 106px height
            self._server_card_component.padding = ft.Padding.symmetric(horizontal=12, vertical=8)

            # Hide the expand/chevron button — card tap navigates to servers instead
            try:
                self._server_card_component._list_btn.visible = False
            except Exception:
                pass

            # Fix vertical alignment of text column inside the card
            try:
                self._server_card_component._content_row.vertical_alignment = ft.CrossAxisAlignment.CENTER
            except Exception:
                pass

            # Wire both click targets to navigate to the Servers page
            _nav_to_servers = lambda e: (self._on_change_server_click(e) if self._on_change_server_click else None)
            self._server_card_component.on_click = _nav_to_servers

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
            [
                left_traffic_column,
                server_card_wrapper,
            ],
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

        # --- Assembly ---
        canvas_layout = ft.Column(
            [
                hero_center_section,
                cards_grid_container,
            ],
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

    def _start_uptime_timer(self):
        """Start background timer loop for uptime counter."""
        if self._timer_running:
            return
        self._timer_running = True
        self._start_time = time.time()

        def timer_loop():
            while self._timer_running and self._is_connected:
                elapsed = int(time.time() - self._start_time)
                hours = elapsed // 3600
                minutes = (elapsed % 3600) // 60
                seconds = elapsed % 60
                uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                self._uptime_text.value = uptime_str
                try:
                    if hasattr(self, "_uptime_text") and self._uptime_text.page:
                        self._uptime_text.update()
                except Exception:
                    break
                time.sleep(1.0)

        self._timer_thread = threading.Thread(target=timer_loop, daemon=True)
        self._timer_thread.start()

    def _stop_uptime_timer(self):
        """Stop background timer loop."""
        self._timer_running = False

    def set_connection_state(
        self,
        is_connected: bool,
        is_connecting: bool = False,
        is_disconnecting: bool = False,
    ):
        """Update connection button state and centerpiece text inside the button."""
        self._is_connected = is_connected

        if is_disconnecting:
            self._toggle_button.set_disconnecting(t("status.disconnecting", default="Disconnecting..."))
            self._stop_uptime_timer()
        elif is_connecting:
            self._toggle_button.set_connecting(t("status.connecting", default="Connecting..."))
            self._uptime_text.value = "00:00:00"
        elif is_connected:
            self._toggle_button.set_connected(t("dashboard.connected", default="Connected"))
            self._start_uptime_timer()
        else:
            self._stop_uptime_timer()
            self._toggle_button.set_disconnected(t("dashboard.disconnected", default="Disconnected"))

        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def set_step(self, step_text: str):
        """Update center status text underneath button."""
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
        """Update live download/upload values and forward activity to connection button."""
        dl_text = speed_text if speed_text is not None else rate_str
        ul_speed_kb = upload_bps / 1024.0
        if ul_speed_kb < 1024.0:
            ul_text = f"{ul_speed_kb:.1f} KB/s"
        else:
            ul_text = f"{(ul_speed_kb / 1024.0):.1f} MB/s"

        self._dl_value_text.value = dl_text
        self._ul_value_text.value = ul_text

        active_total_bps = total_bps if total_bps > 0 else (download_bps + upload_bps)
        self.update_glow_intensity(active_total_bps)

        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def update_glow_intensity(self, total_bps: float = 0.0):
        """Update live throughput for connection button."""
        if self._toggle_button:
            self._toggle_button.update_network_activity(total_bps)

    def update_server_info(self, *args, **kwargs):
        """No-op: ServerCard updates itself via main_window's _update_selected_profile_ui call."""
        pass

    def update_lan_sharing(self, is_enabled: bool, ip_address: str = ""):
        """No-op: LAN sharing is now managed by the top-bar LanSharingCard badge."""
        self._lan_sharing_enabled = is_enabled

    def update_internet_status(self, is_online: bool):
        """Update connection status."""
        self._is_online = is_online

    def update_uptime(self, uptime_str: str):
        """Update uptime timer text underneath central connection button."""
        self._uptime_text.value = uptime_str
        try:
            if hasattr(self, "_uptime_text") and self._uptime_text.page:
                self._uptime_text.update()
        except Exception:
            pass
