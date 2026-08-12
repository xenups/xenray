"""Chain node row component for chain builder page."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class ChainNodeRow(ft.Container):
    """Component for displaying an individual chain node row in chain builder."""

    def __init__(
        self,
        position_label: str,
        position_color: str,
        dropdown: ft.Dropdown,
        item_id: str,
        on_remove: Callable[[str], None],
        disabled: bool = False,
    ):
        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text(
                            position_label,
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=position_color,
                        ),
                        width=60,
                    ),
                    dropdown,
                    ft.IconButton(
                        icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                        icon_size=20,
                        icon_color=ft.Colors.ERROR,
                        tooltip=t("chain.remove_item"),
                        on_click=lambda e: on_remove(item_id),
                        disabled=disabled,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=20, vertical=6),
        )
