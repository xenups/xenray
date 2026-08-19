"""Server Search Bar Component with translucent glass Add Server button."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class ServerSearchBar(ft.Row):
    """Component combining node search input field and glass Add Server action button."""

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
            hint_style=ft.TextStyle(
                color=ft.Colors.with_opacity(0.35, ft.Colors.WHITE),
                size=13,
                weight=ft.FontWeight.W_300,
            ),
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
            prefix_style=ft.TextStyle(color=ft.Colors.with_opacity(0.40, ft.Colors.WHITE)),
            border_radius=12,
            height=42,
            text_size=13,
            text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_300),
            content_padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
            border_color=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            focused_border_color=ft.Colors.with_opacity(0.40, "#A855F7"),
            cursor_color="#A78BFA",
            on_change=lambda e: on_search_change(e.control.value),
            expand=True,
        )

        add_btn = ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ADD_ROUNDED, size=16, color="#E9D5FF"),
                    ft.Text(
                        t("servers.add", default="Add Server"),
                        size=13,
                        color="#E9D5FF",
                        weight=ft.FontWeight.W_400,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=5,
            ),
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.with_opacity(0.15, "#A855F7"),
                side=ft.BorderSide(1.0, ft.Colors.with_opacity(0.40, "#A855F7")),
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            ),
            height=42,
            on_click=on_add_server_click,
        )

        super().__init__(
            controls=[search_field, add_btn],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
