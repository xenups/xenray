"""Server Search Bar Component with Add Server button."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors


class ServerSearchBar(ft.Row):
    """Component combining node search input field and Add Server action button."""

    def __init__(
        self,
        on_search_change: Callable[[str], None],
        on_add_server_click: Callable,
    ):
        search_field = ft.TextField(
            hint_text=t(
                "servers.search_placeholder",
                default="Search server name, region or IP...",
            ),
            prefix_icon=ft.Icons.SEARCH,
            border_radius=24,
            height=44,
            text_style=ft.TextStyle(color=ft.Colors.WHITE),
            content_padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            border_color=AppColors.GLASS_BORDER,
            focused_border_color=AppColors.PRIMARY,
            on_change=lambda e: on_search_change(e.control.value),
            expand=True,
        )

        add_btn = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ADD, size=18, color=ft.Colors.WHITE),
                    ft.Text(
                        t("servers.add", default="Add Server"),
                        size=13,
                        color=ft.Colors.WHITE,
                        weight=ft.FontWeight.W_600,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
            ),
            style=ft.ButtonStyle(
                bgcolor=AppColors.PRIMARY,
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=22),
                padding=ft.Padding.symmetric(horizontal=18, vertical=10),
            ),
            height=44,
            on_click=on_add_server_click,
        )

        super().__init__(
            controls=[search_field, add_btn],
            spacing=12,
        )
