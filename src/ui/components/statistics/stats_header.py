"""Stats Header component with title section and traffic rate badge."""

from __future__ import annotations

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors


class StatsHeader(ft.Row):
    """Header row containing title column and traffic rate badge."""

    def __init__(self, rate_text_control: ft.Text):
        WHITE = ft.Colors.WHITE
        MUTED_WHITE = AppColors.ON_SURFACE_VARIANT
        PURPLE = AppColors.PRIMARY
        CYAN = ft.Colors.CYAN_400

        header_title_col = ft.Column(
            [
                ft.Text(
                    t("nav.statistics", default="Statistics & Analytics"),
                    size=11,
                    weight=ft.FontWeight.W_600,
                    color=MUTED_WHITE,
                ),
                ft.Text(
                    t("dashboard.network_traffic", default="Network Traffic Analytics"),
                    size=20,
                    weight=ft.FontWeight.W_700,
                    color=WHITE,
                ),
            ],
            spacing=2,
        )

        traffic_rate_badge = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.SUBTITLES_OUTLINED, size=14, color=CYAN),
                    rate_text_control,
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border_radius=16,
            bgcolor=ft.Colors.with_opacity(0.14, PURPLE),
            border=ft.Border.all(1.0, ft.Colors.with_opacity(0.3, PURPLE)),
        )

        super().__init__(
            controls=[header_title_col, traffic_rate_badge],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
