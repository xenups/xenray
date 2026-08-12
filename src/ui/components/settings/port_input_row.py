"""Port input settings controls for SOCKS5 and HTTP proxy endpoints."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class PortInputRow(ft.Container):
    """Port input row for settings."""

    def __init__(self, initial_value: int, on_save: Callable):
        self._field = ft.TextField(
            value=str(initial_value),
            width=80,
            height=36,
            text_size=12,
            content_padding=6,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.CENTER,
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.INPUT, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column(
                        [
                            ft.Text(
                                t("settings.socks_port"),
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                "Local SOCKS5 proxy port",
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Row(
                        [
                            self._field,
                            ft.IconButton(
                                icon=ft.Icons.CHECK,
                                icon_size=18,
                                icon_color=ft.Colors.PRIMARY,
                                tooltip=t("settings.save"),
                                on_click=lambda e: on_save(self._field.value),
                            ),
                        ],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
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
        return self._field.value

    def set_border_color(self, color):
        self._field.border_color = color
        self._field.update()


class HttpPortInputRow(ft.Container):
    """HTTP proxy port input row for settings."""

    def __init__(self, initial_value: int, on_save: Callable):
        self._field = ft.TextField(
            value=str(initial_value),
            width=80,
            height=36,
            text_size=12,
            content_padding=6,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.CENTER,
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.HTTP, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column(
                        [
                            ft.Text(
                                t("settings.http_port", default="HTTP Proxy Port"),
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                t(
                                    "settings.http_port_desc",
                                    default="Local HTTP/HTTPS proxy port",
                                ),
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Row(
                        [
                            self._field,
                            ft.IconButton(
                                icon=ft.Icons.CHECK,
                                icon_size=18,
                                icon_color=ft.Colors.PRIMARY,
                                tooltip=t("settings.save"),
                                on_click=lambda e: on_save(self._field.value),
                            ),
                        ],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
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
        return self._field.value

    def set_border_color(self, color):
        self._field.border_color = color
        self._field.update()
