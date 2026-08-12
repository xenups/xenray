"""Engine selector rows for TUN implementation and core proxy selection."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class TunEngineRow(ft.Container):
    """TUN engine selector row with standardized column alignment."""

    def __init__(self, current_engine: str, on_change: Callable):
        self._dropdown = ft.Dropdown(
            width=140,
            text_size=12,
            content_padding=8,
            value=current_engine if current_engine else "sing-box",
            options=[
                ft.dropdown.Option("sing-box", "sing-box"),
                ft.dropdown.Option("xray", "Xray"),
            ],
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
            on_select=on_change,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.SETTINGS_ETHERNET,
                        size=20,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                "TUN Engine",
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                "Core driver engine for VPN TUN mode",
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


class CoreDropdownRow(ft.Container):
    """Core engine selection row (fixed to Xray-core as Outbound/Proxy Engine)."""

    def __init__(self, current_value: str, on_change: Callable):
        self._dropdown = ft.Dropdown(
            width=120,
            text_size=12,
            content_padding=8,
            value="xray",
            options=[
                ft.dropdown.Option("xray", "Xray-core"),
            ],
            disabled=True,
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
            on_select=on_change,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.MEMORY, size=24, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column(
                        [
                            ft.Text(
                                t("settings.core_engine"),
                                size=12,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                t("settings.core_engine_desc"),
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    self._dropdown,
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        )

    @property
    def value(self) -> str:
        return "xray"


class TunEngineDropdownRow(ft.Container):
    """TUN implementation selection row (Xray / Sing-box)."""

    def __init__(self, current_value: str, on_change: Callable):
        self._dropdown = ft.Dropdown(
            width=120,
            text_size=12,
            content_padding=8,
            value=current_value if current_value in ("xray", "singbox") else "singbox",
            options=[
                ft.dropdown.Option("singbox", "Sing-box TUN"),
                ft.dropdown.Option("xray", "Xray TUN"),
            ],
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
            on_select=on_change,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ROUTER, size=24, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column(
                        [
                            ft.Text(
                                t("settings.tun_engine"),
                                size=12,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                t("settings.tun_engine_desc"),
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    self._dropdown,
                ],
                spacing=8,
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
