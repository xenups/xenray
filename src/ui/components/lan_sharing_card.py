"""LAN Proxy Sharing Top Bar Status Chip/Badge & Info Dialog component."""

from __future__ import annotations

import flet as ft

from src.core.i18n import t
from src.utils.network_interface import NetworkInterfaceDetector


class LanSharingCard(ft.Container):
    """Compact LAN Sharing Status Chip/Badge for the top action bar with modal info dialog."""

    def __init__(self, app_context):
        self._app_context = app_context

        # Active Status Dot
        self._status_dot = ft.Container(
            width=6,
            height=6,
            border_radius=3,
            bgcolor=ft.Colors.GREEN_400,
            shadow=ft.BoxShadow(
                blur_radius=4,
                color=ft.Colors.GREEN_400,
            ),
        )

        # Label Text
        self._label_text = ft.Text(
            "LAN",
            size=11,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.GREEN_300,
        )

        super().__init__(
            visible=False,
            padding=ft.Padding.symmetric(horizontal=10, vertical=5),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.GREEN_400),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.35, ft.Colors.GREEN_400)),
            content=ft.Row(
                [
                    self._status_dot,
                    self._label_text,
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            tooltip=t("lan.card_title"),
            on_click=self._open_dialog,
            ink=True,
        )

    def _get_page(self) -> ft.Page | None:
        try:
            return self.page
        except RuntimeError:
            return getattr(self, "_page", None)

    def _copy_to_clipboard(self, text: str, label: str):
        def handler(e):
            page = self._get_page()
            if page:
                try:
                    page.run_task(page.clipboard.set, text)
                    toast_mgr = getattr(page, "_toast_manager", None)
                    if toast_mgr:
                        toast_mgr.show(f"{label} {t('lan.copied')}", "success")
                except Exception:
                    pass

        return handler

    def _open_dialog(self, e=None):
        """Open the LAN Proxy Sharing info dialog."""
        page = self._get_page()
        if not page:
            return

        port = self._app_context.settings.get_proxy_port()
        http_port = self._app_context.settings.get_http_port()
        lan_ip = NetworkInterfaceDetector.get_primary_lan_ip() or t("lan.unknown_ip")
        telegram_url = f"t.me/socks?server={lan_ip}&port={port}"

        def close_dialog(evt=None):
            p = self._get_page()
            if p:
                try:
                    p.pop_dialog()
                except Exception:
                    pass

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.WIFI_ROUNDED, color=ft.Colors.GREEN_400, size=22),
                    ft.Text(t("lan.card_title"), size=14, weight=ft.FontWeight.BOLD),
                ],
                spacing=8,
            ),
            content=ft.Container(
                width=340,
                content=ft.Column(
                    [
                        # Local IP Row
                        ft.Row(
                            [
                                ft.Text(t("lan.local_ip"), size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                                ft.Text(lan_ip, size=12, weight=ft.FontWeight.BOLD, selectable=True, expand=True),
                                ft.IconButton(
                                    icon=ft.Icons.COPY_ROUNDED,
                                    icon_size=14,
                                    tooltip=t("lan.copy_ip"),
                                    on_click=self._copy_to_clipboard(lan_ip, "IP"),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        # SOCKS5 Port Row
                        ft.Row(
                            [
                                ft.Text(t("lan.socks5_port"), size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                                ft.Text(str(port), size=12, weight=ft.FontWeight.BOLD, selectable=True, expand=True),
                                ft.IconButton(
                                    icon=ft.Icons.COPY_ROUNDED,
                                    icon_size=14,
                                    tooltip=t("lan.copy_port"),
                                    on_click=self._copy_to_clipboard(str(port), "SOCKS5 Port"),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        # HTTP Port Row
                        ft.Row(
                            [
                                ft.Text(t("lan.http_port"), size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                                ft.Text(
                                    str(http_port), size=12, weight=ft.FontWeight.BOLD, selectable=True, expand=True
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.COPY_ROUNDED,
                                    icon_size=14,
                                    tooltip=t("lan.copy_port"),
                                    on_click=self._copy_to_clipboard(str(http_port), "HTTP Port"),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(height=1, color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE_VARIANT)),
                        ft.Text(t("lan.guide_title"), size=11, weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY),
                        # Telegram Link Row
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.SEND_ROUNDED, size=13, color=ft.Colors.BLUE_400),
                                ft.Text(f"{t('lan.telegram')} ", size=10, color=ft.Colors.ON_SURFACE_VARIANT),
                                ft.Text(
                                    telegram_url,
                                    size=10,
                                    weight=ft.FontWeight.W_500,
                                    color=ft.Colors.BLUE_300,
                                    selectable=True,
                                    expand=True,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.COPY_ROUNDED,
                                    icon_size=14,
                                    tooltip=t("lan.copy_tg"),
                                    on_click=self._copy_to_clipboard(telegram_url, "Telegram Link"),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=4,
                        ),
                        # Wi-Fi Setup Row
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.WIFI_ROUNDED, size=13, color=ft.Colors.AMBER_400),
                                ft.Text(f"{t('lan.wifi')} ", size=10, color=ft.Colors.ON_SURFACE_VARIANT),
                                ft.Text(
                                    f"{lan_ip}:{port + 4} ({t('lan.type_http')})",
                                    size=10,
                                    weight=ft.FontWeight.W_500,
                                    selectable=True,
                                    expand=True,
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=4,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("Close", on_click=close_dialog),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        page.show_dialog(dialog)

    def set_visible(self, show: bool) -> None:
        """Show or hide the top bar badge; refreshes LAN IP when shown."""
        if show:
            lan_ip = NetworkInterfaceDetector.get_primary_lan_ip()
            if lan_ip:
                self._label_text.value = f"LAN {lan_ip}"
            else:
                self._label_text.value = "LAN"
        self.visible = show
        try:
            self.update()
        except RuntimeError:
            # Control not attached to a page yet — nothing to refresh.
            pass
