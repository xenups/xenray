"""Stat Card Component for statistics page analytics display."""

from __future__ import annotations

from typing import Optional

import flet as ft

from src.ui.theme import AppColors, create_glass_container


class StatCard(ft.Container):
    """Reusable stat card container displaying title, primary metric, and secondary sub-metric."""

    def __init__(
        self,
        title: str,
        val_control: ft.Text,
        sub_title: str,
        sub_val_control: ft.Text,
        icon: ft.IconData,
        icon_color: str,
    ):
        self._val_control = val_control
        self._sub_val_control = sub_val_control
        card_content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(icon, size=15, color=icon_color),
                            width=26,
                            height=26,
                            border_radius=13,
                            bgcolor=ft.Colors.with_opacity(0.16, icon_color),
                            alignment=ft.Alignment.CENTER,
                        ),
                        ft.Text(
                            title,
                            size=11,
                            weight=ft.FontWeight.W_600,
                            color=AppColors.ON_SURFACE_VARIANT,
                            expand=True,
                        ),
                    ],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                val_control,
                ft.Row(
                    [
                        ft.Text(sub_title, size=11, color=AppColors.ON_SURFACE_VARIANT),
                        sub_val_control,
                    ],
                    spacing=2,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=6,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        glass_card = create_glass_container(
            content=card_content,
            expand=True,
            padding=14,
            height=110,
        )

        super().__init__(
            content=glass_card.content,
            expand=glass_card.expand,
            padding=glass_card.padding,
            height=glass_card.height,
            bgcolor=glass_card.bgcolor,
            border=glass_card.border,
            border_radius=glass_card.border_radius,
            blur=glass_card.blur,
        )

    def update_telemetry(self, value: str, sub_value: Optional[str] = None) -> None:
        """Reactively update the primary metric and optional sub-metric values."""
        self._val_control.value = value
        if sub_value is not None:
            self._sub_val_control.value = sub_value
        try:
            self.update()
        except Exception:
            pass
