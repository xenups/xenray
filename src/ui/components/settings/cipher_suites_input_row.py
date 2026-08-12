"""Cipher suites input row for TLS/REALITY settings."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class CipherSuitesInputRow(ft.Container):
    """Cipher suites input row for TLS/REALITY settings."""

    def __init__(self, initial_value: str, on_save: Callable):
        self._field = ft.TextField(
            value=initial_value,
            width=280,
            height=40,
            text_size=12,
            content_padding=8,
            hint_text=t("settings.cipher_suites_hint"),
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
        )
        self._example_text = ft.Text(
            t("settings.cipher_suites_example"),
            size=10,
            color=ft.Colors.OUTLINE,
        )

        super().__init__(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.SECURITY,
                                size=24,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        t("settings.cipher_suites"),
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    ft.Text(
                                        t("settings.cipher_suites_desc"),
                                        size=11,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CHECK,
                                icon_size=20,
                                icon_color=ft.Colors.PRIMARY,
                                tooltip=t("settings.save"),
                                on_click=lambda e: on_save(self._field.value),
                            ),
                        ],
                        spacing=5,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [self._field],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [self._example_text],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                spacing=4,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        )

    @property
    def value(self) -> str:
        return self._field.value

    def set_border_color(self, color):
        self._field.border_color = color
        self._field.update()
