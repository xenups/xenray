"""Reusable MetricCard component for telemetry and status displays."""

from __future__ import annotations

import flet as ft

from src.ui.theme import AppColors, create_glass_container


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
                ft.Icon(icon, size=16, color=icon_color),
                ft.Text(
                    title,
                    size=11,
                    weight=ft.FontWeight.W_600,
                    color=AppColors.ON_SURFACE_VARIANT,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
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

        glass = create_glass_container(
            content=content_column,
            padding=padding,
            border_radius=12,
        )

        super().__init__(
            content=glass.content,
            bgcolor=glass.bgcolor,
            border=glass.border,
            border_radius=glass.border_radius,
            padding=glass.padding,
            expand=expand,
            height=height,
        )
