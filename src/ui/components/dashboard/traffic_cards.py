"""Traffic Cards Component - compact 185px Download & Upload throughput display cards."""

from __future__ import annotations

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors


class TrafficCards(ft.Column):
    """Left column containing compact Download and Upload live traffic cards."""

    def __init__(self) -> None:
        WHITE = ft.Colors.WHITE
        MUTED_WHITE = AppColors.ON_SURFACE_VARIANT

        self._dl_value_text = ft.Text("0.0 MB/s", size=13, weight=ft.FontWeight.W_700, color=WHITE)
        self._ul_value_text = ft.Text("0.0 MB/s", size=13, weight=ft.FontWeight.W_700, color=WHITE)

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
                                t("dashboard.download", default="Download"),
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
            bgcolor=ft.Colors.with_opacity(0.035, WHITE),
            border=None,
        )

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
                                t("dashboard.upload", default="Upload"),
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
            bgcolor=ft.Colors.with_opacity(0.035, WHITE),
            border=None,
        )

        super().__init__(
            controls=[download_card, upload_card],
            width=185,
            spacing=8,
            height=106,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def update_speeds(self, download_text: str, upload_text: str) -> None:
        """Update download and upload text values."""
        self._dl_value_text.value = download_text
        self._ul_value_text.value = upload_text
