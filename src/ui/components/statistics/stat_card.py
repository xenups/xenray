"""Stat Card Component for statistics page analytics display."""

from __future__ import annotations

from typing import Optional

import flet as ft


class StatCard(ft.Container):
    """Reusable stat card column displaying title, primary metric, and secondary sub-metric."""

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

        val_control.size = 18
        val_control.weight = ft.FontWeight.W_300
        val_control.color = ft.Colors.WHITE

        card_content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(
                            width=6,
                            height=6,
                            border_radius=3,
                            bgcolor=icon_color,
                        ),
                        ft.Text(
                            title,
                            size=11,
                            weight=ft.FontWeight.W_300,
                            color=ft.Colors.with_opacity(0.65, ft.Colors.WHITE),
                            expand=True,
                        ),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                val_control,
                ft.Row(
                    [
                        ft.Text(
                            sub_title,
                            size=10,
                            weight=ft.FontWeight.W_200,
                            color=ft.Colors.with_opacity(0.40, ft.Colors.WHITE),
                        ),
                        sub_val_control,
                    ],
                    spacing=3,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=4,
            alignment=ft.MainAxisAlignment.CENTER,
        )

        super().__init__(
            content=card_content,
            expand=True,
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            bgcolor=ft.Colors.TRANSPARENT,
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
