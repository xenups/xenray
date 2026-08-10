"""LAN Proxy QR Code card component."""

from __future__ import annotations

import flet as ft

from src.core.i18n import t


class QRCard(ft.Container):
    """Container holding Scan to Connect text and QR image box."""

    def __init__(self, qr_box: ft.Container, is_rtl: bool = False):
        super().__init__(
            bgcolor="#13141C",
            border_radius=10,
            padding=8,
            alignment=ft.Alignment.CENTER,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
            content=ft.Column(
                [
                    ft.Text(
                        t("lan_sharing.scan_to_connect", default="Scan to Connect"),
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color="white",
                        rtl=is_rtl,
                    ),
                    qr_box,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            ),
        )
