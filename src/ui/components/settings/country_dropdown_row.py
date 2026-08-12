"""Country dropdown selection row for direct routing bypass."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class CountryDropdownRow(ft.Container):
    """Country dropdown row for direct routing settings."""

    def __init__(self, current_value: str, on_change: Callable):
        self._dropdown = ft.Dropdown(
            width=140,
            text_size=12,
            content_padding=8,
            value=current_value if current_value else "none",
            options=[
                ft.dropdown.Option("none", t("countries.none")),
                ft.dropdown.Option("ir", "🇮🇷 " + t("countries.ir")),
                ft.dropdown.Option("cn", "🇨🇳 " + t("countries.cn")),
                ft.dropdown.Option("ru", "🇷🇺 " + t("countries.ru")),
            ],
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
        )

        original_on_change = on_change

        def wrapped_on_change(e):
            val = self._dropdown.value
            if hasattr(e, "control") and e.control and hasattr(e.control, "value") and e.control.value:
                val = e.control.value
            original_on_change(val)

        self._dropdown.on_select = wrapped_on_change
        self._dropdown.on_change = wrapped_on_change

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.PUBLIC, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column(
                        [
                            ft.Text(
                                t("settings.direct_country"),
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                "Bypass proxy for specified country traffic",
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    self._dropdown,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        )

    @property
    def value(self) -> str:
        return self._dropdown.value
