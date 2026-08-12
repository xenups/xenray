"""Traffic Cards Component - compact 185px Download & Upload throughput display cards."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors


class TrafficCards(ft.Column):
    """Left column containing compact Download and Upload live traffic cards."""

    def __init__(self, on_card_click: Optional[Callable] = None) -> None:
        self._on_card_click = on_card_click

        WHITE = ft.Colors.WHITE
        MUTED_WHITE = AppColors.ON_SURFACE_VARIANT

        self._dl_value_text = ft.Text("0.0 MB/s", size=13, weight=ft.FontWeight.W_700, color=WHITE)
        self._ul_value_text = ft.Text("0.0 MB/s", size=13, weight=ft.FontWeight.W_700, color=WHITE)

        download_card = self._build_card(
            icon=ft.Icons.SOUTH_WEST_ROUNDED,
            icon_color="#38bdf8",
            label=t("dashboard.download", default="Download"),
            value_text=self._dl_value_text,
            muted_white=MUTED_WHITE,
            white=WHITE,
            on_click=self._on_card_click,
        )

        upload_card = self._build_card(
            icon=ft.Icons.NORTH_EAST_ROUNDED,
            icon_color="#c084fc",
            label=t("dashboard.upload", default="Upload"),
            value_text=self._ul_value_text,
            muted_white=MUTED_WHITE,
            white=WHITE,
            on_click=self._on_card_click,
        )

        super().__init__(
            controls=[download_card, upload_card],
            width=185,
            spacing=8,
            height=124,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def _build_card(
        self,
        icon: ft.IconData,
        icon_color: str,
        label: str,
        value_text: ft.Text,
        muted_white: str,
        white: str,
        on_click: Optional[Callable] = None,
    ) -> ft.Container:
        """Build one speed card: fixed icon box (left) + expanding text column.

        The icon sits in a strict 42x42 box anchored on the left with its own
        12px right margin, while the label/value column expands to fill the rest
        of the card — so speed strings of any length grow strictly to the right
        without shifting the icon (zero jitter) or clustering to one side.
        """
        icon_box = ft.Container(
            content=ft.Icon(icon, size=18, color=icon_color),
            width=42,
            height=42,
            border_radius=13,
            bgcolor=ft.Colors.with_opacity(0.14, icon_color),
            alignment=ft.Alignment.CENTER,
            margin=ft.Margin.only(right=10),
        )

        text_column = ft.Column(
            [
                ft.Text(label, size=10, color=muted_white, weight=ft.FontWeight.W_500),
                value_text,
            ],
            spacing=1,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.START,
            width=105,
        )

        return ft.Container(
            content=ft.Row(
                [icon_box, text_column],
                spacing=0,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=185,
            height=58,
            padding=ft.Padding.symmetric(vertical=8, horizontal=14),
            alignment=ft.Alignment.CENTER,
            border_radius=14,
            bgcolor=ft.Colors.with_opacity(0.035, white),
            border=None,
            on_click=on_click if on_click else (lambda e: None),
            on_hover=lambda e: None,
        )

    def update_speeds(self, download_text: str, upload_text: str) -> None:
        """Update download and upload text values."""
        self._dl_value_text.value = download_text
        self._ul_value_text.value = upload_text
        try:
            if self.page:
                self.update()
        except Exception:
            pass
