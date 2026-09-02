"""Stats Header component with clean title and minimal traffic rate badge."""

from __future__ import annotations

import flet as ft

from src.core.i18n import t


class StatsHeader(ft.Row):
    """Header row containing title and minimal traffic rate badge."""

    def __init__(self, rate_text_control: ft.Text):
        self._rate_text_control = rate_text_control

        title_text = ft.Text(
            t("nav.statistics", default="Network Traffic"),
            size=18,
            weight=ft.FontWeight.W_300,
            style=ft.TextStyle(letter_spacing=0.8),
            color=ft.Colors.WHITE,
        )

        traffic_rate_badge = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        width=6,
                        height=6,
                        border_radius=3,
                        bgcolor="#38BDF8",
                    ),
                    rate_text_control,
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
            border=ft.Border.all(1.0, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
        )

        super().__init__(
            controls=[title_text, traffic_rate_badge],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def update_rate(self, rate_str: str) -> None:
        """Reactively update the live traffic rate badge text."""
        self._rate_text_control.value = rate_str
        try:
            self.update()
        except Exception:
            pass
