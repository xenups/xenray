"""Routing rule item row component."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class RuleItemRow(ft.Container):
    """Component for displaying and deleting a single routing rule."""

    def __init__(self, item: str, on_delete: Callable[[str], None]):
        super().__init__(
            content=ft.Row(
                [
                    ft.Text(item, size=14, weight=ft.FontWeight.W_500, expand=True),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE,
                        icon_size=20,
                        icon_color=ft.Colors.RED_400,
                        tooltip=t("routing.remove"),
                        on_click=lambda e: on_delete(item),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=5),
            border=ft.Border.only(bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )
