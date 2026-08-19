"""Window Title Bar Component - Draggable frameless app title bar with branding and window controls."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.constants import APP_VERSION
from src.core.i18n import t


class WindowTitleBar(ft.Container):
    """Frameless window top bar with branding (left) and minimize/close buttons (right)."""

    def __init__(
        self,
        on_minimize: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
    ):
        header_branding = ft.Row(
            [
                ft.Image(
                    src="icon.png",
                    width=20,
                    height=20,
                    fit="contain",
                ),
                ft.Text(
                    "XenRay",
                    size=14,
                    weight=ft.FontWeight.W_800,
                    color=ft.Colors.WHITE,
                ),
                ft.Container(
                    content=ft.Text(
                        f"v{APP_VERSION}",
                        size=10,
                        color="#8A8F9E",
                    ),
                    margin=ft.Margin.only(top=4),
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        window_actions = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.MINIMIZE_ROUNDED,
                    icon_size=14,
                    icon_color=ft.Colors.with_opacity(0.65, ft.Colors.WHITE),
                    tooltip=t("window.minimize"),
                    on_click=on_minimize,
                ),
                ft.IconButton(
                    icon=ft.Icons.CLOSE_ROUNDED,
                    icon_size=14,
                    icon_color=ft.Colors.with_opacity(0.8, "#f43f5e"),
                    tooltip=t("window.close"),
                    on_click=on_close,
                ),
            ],
            spacing=2,
        )

        super().__init__(
            content=ft.WindowDragArea(
                content=ft.Row(
                    [
                        header_branding,
                        window_actions,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
            ),
            height=36,
            padding=ft.Padding.only(right=8, left=14, top=4),
        )
