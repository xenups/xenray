"""Stat Card Component for statistics page analytics display."""

from __future__ import annotations

import flet as ft

from src.ui.theme import AppColors, create_glass_container


class StatCard(ft.Container):
    """Reusable stat card container displaying title, primary metric, and secondary sub-metric."""

    def __init__(
        self,
        title: str,
        val_control: ft.Control,
        sub_title: str,
        sub_val_control: ft.Control,
        icon: str,
        icon_color: str,
    ):
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
                        ),
                    ],
                    spacing=8,
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
