"""LAN IP / Port micro-chip component with copy action."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import t


class MicroChip(ft.Container):
    """Reusable micro chip container for displaying IP/Port details with copy button."""

    def __init__(
        self,
        label_key: str,
        default_label: str,
        value: str,
        val_text_ctrl: Optional[ft.Text] = None,
        on_copy: Optional[Callable[[str], None]] = None,
        is_rtl: bool = False,
    ):
        val_ctrl = val_text_ctrl or ft.Text(
            value,
            size=11,
            weight=ft.FontWeight.BOLD,
            color="white",
            selectable=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        copy_btn = ft.IconButton(
            icon=ft.Icons.COPY,
            icon_size=14,
            icon_color="#8B5CF6",
            on_click=lambda e, v=value: on_copy(v) if on_copy else None,
            style=ft.ButtonStyle(padding=ft.Padding.all(2)),
        )

        super().__init__(
            expand=1,
            bgcolor="#13141C",
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            border_radius=8,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
            content=ft.Row(
                [
                    copy_btn,
                    ft.Column(
                        [
                            ft.Text(
                                t(label_key, default=default_label),
                                size=10,
                                color="#8E8C99",
                                weight=ft.FontWeight.W_500,
                                rtl=is_rtl,
                            ),
                            val_ctrl,
                        ],
                        spacing=1,
                        expand=True,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
