"""Reusable MetricCard component for telemetry and status displays."""

from __future__ import annotations

import flet as ft


class MetricCard(ft.Container):
    """Reusable glass metric card container with equal flex dimensions."""

    def __init__(
        self,
        icon: str,
        icon_color: str,
        title: str,
        value_control: ft.Control,
        footer_control: ft.Control,
        height: int = 110,
        padding: int = 14,
        expand: int = 1,
    ):
        header_row = ft.Row(
            [
                ft.Text(
                    title,
                    size=11,
                    weight=ft.FontWeight.W_400,
                    color="#94A3B8",
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
        )

        content_column = ft.Column(
            [
                header_row,
                value_control,
                footer_control,
            ],
            spacing=4,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        super().__init__(
            content=content_column,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
            border_radius=12,
            padding=padding,
            expand=expand,
            height=height,
        )
