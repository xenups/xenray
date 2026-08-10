"""Routing toggle row component."""

from __future__ import annotations

from typing import Callable

import flet as ft


class RoutingToggleRow(ft.Container):
    """Component for quick routing toggle settings."""

    def __init__(
        self,
        key: str,
        title: str,
        subtitle: str,
        icon: str,
        initial_value: bool,
        on_change: Callable[[str, bool], None],
    ):
        self._key = key
        self._on_change = on_change

        switch = ft.Switch(
            value=initial_value,
            on_change=lambda e: self._on_change(self._key, e.control.value),
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(icon, size=20, color=ft.Colors.PRIMARY),
                    ft.Column(
                        [
                            ft.Text(title, size=13, weight=ft.FontWeight.W_500),
                            ft.Text(subtitle, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    switch,
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=15, vertical=12),
            border=ft.Border.only(bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )
