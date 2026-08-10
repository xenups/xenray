"""App Update Card component for Settings Page."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors, create_glass_container


class UpdateCard(ft.Container):
    """Card displaying client version info and Check for Updates action button."""

    def __init__(self, on_check_update_click: Callable):
        WHITE = ft.Colors.WHITE

        info_col = ft.Column(
            [
                ft.Text(
                    "XenRay Client",
                    size=14,
                    weight=ft.FontWeight.W_700,
                    color=WHITE,
                ),
                ft.Text(
                    t("settings.version", default="v1.0.0"),
                    size=12,
                    color=AppColors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=2,
        )

        update_btn = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT, size=15, color=WHITE),
                    ft.Text(
                        t("settings.check_updates", default="Check for Updates"),
                        size=12,
                        color=AppColors.ON_PRIMARY,
                        weight=ft.FontWeight.W_600,
                    ),
                ],
                spacing=6,
            ),
            style=ft.ButtonStyle(
                bgcolor=AppColors.PRIMARY,
                color=AppColors.ON_PRIMARY,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            ),
            on_click=on_check_update_click,
        )

        glass = create_glass_container(
            content=ft.Row(
                [info_col, update_btn],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

        super().__init__(
            content=glass.content,
            bgcolor=glass.bgcolor,
            border=glass.border,
            border_radius=glass.border_radius,
            blur=glass.blur,
            padding=glass.padding,
        )
