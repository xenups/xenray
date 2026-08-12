"""DNS server row component."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class DNSServerRow(ft.Container):
    """Component for displaying and managing a DNS server entry."""

    def __init__(self, idx: int, item: dict, on_move_up: Callable[[int], None], on_delete: Callable[[int], None]):
        proto = item.get("protocol", "udp").upper()
        addr = item.get("address", "?")

        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text(
                            proto,
                            size=10,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.ON_SURFACE if proto in ["UDP", "TCP"] else ft.Colors.ON_PRIMARY_CONTAINER,
                        ),
                        bgcolor=ft.Colors.BLUE_200 if proto in ["UDP", "TCP"] else ft.Colors.GREEN_200,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                        border_radius=4,
                        width=50,
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Text(
                        addr,
                        size=13,
                        weight=ft.FontWeight.W_500,
                        expand=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        color=ft.Colors.ON_SURFACE,
                    ),
                    ft.Row(
                        [
                            ft.IconButton(
                                ft.Icons.ARROW_UPWARD,
                                icon_size=18,
                                tooltip=t("dns.move_up"),
                                on_click=lambda e: on_move_up(idx),
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                icon_size=18,
                                icon_color=ft.Colors.RED_400,
                                tooltip=t("dns.remove"),
                                on_click=lambda e: on_delete(idx),
                            ),
                        ],
                        spacing=0,
                        alignment=ft.MainAxisAlignment.END,
                        width=80,
                    ),
                ]
            ),
            padding=ft.Padding.symmetric(horizontal=20, vertical=12),
            border=ft.Border.only(bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
            bgcolor=ft.Colors.with_opacity(0.15, "#1e293b"),
        )
