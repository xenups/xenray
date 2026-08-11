"""LAN Proxy Sharing Page - full-page dedicated view with live QR code, settings state sync, and real-time toggle update."""

from __future__ import annotations

import asyncio
from typing import Callable, Optional

import flet as ft

from src.core.event_bus import TOPIC_LAN_SHARING_CHANGED, event_bus
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

        self._ip_chip = MicroChip(
            "lan_sharing.local_ip",
            "Local IP",
            self.local_ip,
            on_copy=self._copy,
            is_rtl=self.is_rtl,
        )

        badges_row = ft.Row(
            controls=[
                self._ip_chip,
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

        self._qr_card = QRCard(is_rtl=self.is_rtl)
        if self.allow_lan:
            qr_str = self._controller.generate_qr(self.local_ip, self.http_port)
            self._qr_card.update_qr(qr_str)
        else:
            self._qr_card.set_qr_visible(False)

        guide_card = ConnectionGuideCard(is_rtl=self.is_rtl)

        self.content = ft.Column(
            controls=[
                header_row,
                badges_row,
                self._qr_card,
                guide_card,
            ],
            spacing=6,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        event_bus.subscribe(TOPIC_LAN_SHARING_CHANGED, self._on_lan_sharing_changed)

    def dispose(self) -> None:
        """Release the EventBus subscription held by this view."""
        event_bus.unsubscribe(TOPIC_LAN_SHARING_CHANGED, self._on_lan_sharing_changed)

    def _on_lan_sharing_changed(self, data) -> None:
        """Sync this page's switch + QR card when LAN sharing changes anywhere."""
        if not isinstance(data, dict):
            return
        enabled = bool(data.get("enabled", self.allow_lan))
        if enabled == self.allow_lan:
            return

        self.allow_lan = enabled
        self._master_switch.value = enabled

        if enabled:
            self.local_ip = self._controller.get_local_ip()
            self._ip_chip.update_value(self.local_ip)
            self._qr_card.show_loading()
            self._refresh_qr_async(True)
        else:
            self._qr_card.set_qr_visible(False)

        try:
            if self._master_switch.page:
                self._master_switch.update()
        except Exception:
            pass

    def _refresh_qr_async(self, enabled: bool) -> None:
        """Refresh QR content off the UI thread, falling back to sync when headless."""
        if not enabled:
            return
        try:
            page = self.page
        except RuntimeError:
            page = None
        if page is not None:
            page.run_task(self._generate_qr_async)
        else:
            self._generate_qr_sync()

    async def _generate_qr_async(self) -> None:
        """Generate the QR base64 in a worker thread so the UI never blocks."""
        qr_str = await asyncio.to_thread(self._controller.generate_qr, self.local_ip, self.http_port)
        self._apply_qr_result(qr_str)

    def _generate_qr_sync(self) -> None:
        """Synchronous QR generation used only when no live page is attached."""
        qr_str = self._controller.generate_qr(self.local_ip, self.http_port)
        self._apply_qr_result(qr_str)

    def _apply_qr_result(self, qr_str: Optional[str]) -> None:
        """Apply a resolved QR result through the QR card component."""
        self._qr_card.update_qr(qr_str)

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
        """Handle LAN switch toggle in real-time (UI state first, QR resolved async)."""
        try:
            enabled = e.control.value
            self.allow_lan = enabled
            self._controller.set_lan_sharing_enabled(enabled)

            self.local_ip = self._controller.get_local_ip()
            self._ip_chip.update_value(self.local_ip)

            if enabled:
                self._qr_card.show_loading()
            else:
                self._qr_card.set_qr_visible(False)

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

            self._refresh_qr_async(enabled)
        except Exception:
            pass


# Backward-compatibility alias
LanSharingView = LanSharingPage
