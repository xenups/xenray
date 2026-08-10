"""LAN Proxy Sharing Page - full-page dedicated view with live QR code, settings state sync, and real-time toggle update."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import get_language, t
from src.services.lan_service import LanService
from src.ui.components.dashboard.connection_guide_card import ConnectionGuideCard
from src.ui.components.lan import MicroChip, QRCard
from src.ui.controllers.lan_sharing_controller import LanSharingController

# Aliases for backward compatibility
get_real_physical_lan_ip = LanService.get_real_physical_lan_ip
get_real_local_ip = LanService.get_real_physical_lan_ip
generate_qr_base64 = LanService.generate_qr_base64


class LanSharingPage(ft.Container):
    """Dedicated full-page LAN Proxy Sharing Page with real-time toggle updates."""

    def __init__(
        self,
        app_context=None,
        on_back: Optional[Callable] = None,
        on_lan_toggle: Optional[Callable[[bool], None]] = None,
    ):
        super().__init__()
        self.expand = True
        self.padding = 12

        self._app_context = app_context
        self._on_back = on_back
        self._on_lan_toggle = on_lan_toggle
        self.is_rtl = get_language() == "fa"

        self._controller = LanSharingController(app_context=app_context)
        self.local_ip = self._controller.get_local_ip()
        self.http_port = self._controller.get_http_port()
        self.socks_port = self._controller.get_socks_port()
        self.allow_lan = self._controller.get_allow_lan()

        self._master_switch = ft.Switch(
            value=self.allow_lan,
            active_color="#4ADE80",
            on_change=self._on_toggle_change,
        )

        header_row = ft.Row(
            controls=[
                ft.Column(
                    [
                        ft.Text(
                            t("lan_sharing.title", default="LAN Proxy Sharing"),
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color="white",
                            rtl=self.is_rtl,
                        ),
                        ft.Text(
                            t(
                                "lan_sharing.subtitle",
                                default="Share your proxy connection across devices on your local network",
                            ),
                            size=11,
                            color="#8E8C99",
                            rtl=self.is_rtl,
                        ),
                    ],
                    spacing=2,
                ),
                self._master_switch,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._ip_text_ctrl = ft.Text(
            self.local_ip,
            size=11,
            weight=ft.FontWeight.BOLD,
            color="white",
            selectable=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        badges_row = ft.Row(
            controls=[
                MicroChip(
                    "lan_sharing.local_ip",
                    "Local IP",
                    self.local_ip,
                    val_text_ctrl=self._ip_text_ctrl,
                    on_copy=self._copy,
                    is_rtl=self.is_rtl,
                ),
                MicroChip(
                    "lan_sharing.http_port",
                    "HTTP Port",
                    self.http_port,
                    on_copy=self._copy,
                    is_rtl=self.is_rtl,
                ),
                MicroChip(
                    "lan_sharing.socks_port",
                    "SOCKS5 Port",
                    self.socks_port,
                    on_copy=self._copy,
                    is_rtl=self.is_rtl,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=6,
        )

        self._qr_box = ft.Container(
            width=170,
            height=170,
            border_radius=8,
            padding=4,
            alignment=ft.Alignment.CENTER,
        )
        self._update_qr_box(self.allow_lan)

        qr_card = QRCard(qr_box=self._qr_box, is_rtl=self.is_rtl)
        guide_card = ConnectionGuideCard(is_rtl=self.is_rtl)

        self.content = ft.Column(
            controls=[
                header_row,
                badges_row,
                qr_card,
                guide_card,
            ],
            spacing=6,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def _update_qr_box(self, enabled: bool) -> None:
        """Update QR box content dynamically in real-time when switch is toggled."""
        if enabled:
            qr_str = self._controller.generate_qr(self.local_ip, self.http_port)
            if qr_str:
                self._qr_box.bgcolor = "white"
                self._qr_box.content = ft.Image(
                    src=f"data:image/png;base64,{qr_str}",
                    width=170,
                    height=170,
                    fit=ft.BoxFit.CONTAIN,
                )
                return

        self._qr_box.bgcolor = "#13141C"
        self._qr_box.content = ft.Column(
            [
                ft.Icon(
                    ft.Icons.WIFI_OFF_ROUNDED,
                    size=34,
                    color=ft.Colors.with_opacity(0.35, ft.Colors.WHITE),
                ),
                ft.Text(
                    t("lan_sharing.disabled_placeholder", default="LAN Sharing Disabled"),
                    color="grey",
                    size=10,
                    rtl=self.is_rtl,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        )

    def _copy(self, value: str) -> None:
        try:
            page = self.page
            if page:
                page.run_task(page.clipboard.set, value)
                toast_mgr = getattr(page, "_toast_manager", None)
                if toast_mgr:
                    copied_label = t("lan.copied", default="copied!")
                    toast_mgr.show(f"{value} {copied_label}", "success", 2000)
        except Exception:
            pass

    def _on_toggle_change(self, e) -> None:
        """Handle LAN switch toggle in real-time."""
        try:
            enabled = e.control.value
            self.allow_lan = enabled
            self._controller.set_allow_lan(enabled)

            self.local_ip = self._controller.get_local_ip()
            self._ip_text_ctrl.value = self.local_ip
            self._update_qr_box(enabled)

            if self._on_lan_toggle:
                self._on_lan_toggle(enabled)

            try:
                if self.page:
                    sidebar = getattr(self.page, "_nav_sidebar", None)
                    if not sidebar and hasattr(self.page, "_window"):
                        sidebar = getattr(self.page._window, "_nav_sidebar", None)
                    if sidebar and hasattr(sidebar, "update_lan_badge"):
                        sidebar.update_lan_badge(enabled)
            except Exception:
                pass
        except Exception:
            pass


# Backward-compatibility alias
LanSharingView = LanSharingPage
