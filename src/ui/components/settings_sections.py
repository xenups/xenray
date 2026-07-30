"""Reusable settings section components with i18n and RTL support."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import is_rtl, t
from src.ui.components.settings.settings_section_builders import (
    LanguageDropdownRow,
    ModeRadioCards,
    ModeSwitchRow,
    SettingsSection,
    StartupToggleRow,
    TunEngineRow,
    rtl_aware,
)
from src.ui.theme import AppColors


class SettingsListTile(ft.Container):
    """A styled list tile for settings navigation with standardized column alignment."""

    def __init__(self, icon: str, title: str, subtitle: str = "", on_click=None, show_chevron: bool = True):
        trailing = (
            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=ft.Colors.OUTLINE)
            if show_chevron
            else ft.Container(width=0)
        )
        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(icon, size=20, color=ft.Colors.WHITE),
                        width=28,
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                    ft.Column(
                        [
                            ft.Text(title, size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                            ft.Text(subtitle, size=12, color=ft.Colors.ON_SURFACE_VARIANT)
                            if subtitle
                            else ft.Container(height=0),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    trailing,
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            border_radius=10,
            ink=True if on_click else False,
            on_click=on_click,
        )


class PortInputRow(ft.Container):
    """Port input row for settings with standardized column alignment."""

    def __init__(self, initial_value: int, on_save: Callable):
        self._field = ft.TextField(
            value=str(initial_value),
            width=80,
            height=38,
            text_size=12,
            content_padding=8,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.CENTER,
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=AppColors.PRIMARY,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.INPUT, size=20, color=ft.Colors.WHITE),
                        width=28,
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                    ft.Column(
                        [
                            ft.Text(t("settings.socks_port", default="Local Inbound Port"), size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                            ft.Text(t("settings.socks_port_desc", default="SOCKS5 & HTTP listening port"), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
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
                                icon_color=ft.Colors.WHITE,
                                tooltip=t("settings.save"),
                                on_click=lambda e: on_save(self._field.value),
                            ),
                        ],
                        spacing=4,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            border_radius=10,
        )

    @property
    def value(self) -> str:
        return self._field.value


class CountryDropdownRow(ft.Container):
    """Country dropdown row for direct routing settings with standardized column alignment."""

    def __init__(self, current_value: str, on_change: Callable):
        self._on_change = on_change
        self._dropdown = ft.Dropdown(
            width=140,
            height=38,
            text_size=12,
            content_padding=8,
            value=current_value if current_value else "none",
            options=[
                ft.dropdown.Option("none", t("countries.none", default="None")),
                ft.dropdown.Option("ir", t("countries.ir", default="Iran")),
                ft.dropdown.Option("cn", t("countries.cn", default="China")),
                ft.dropdown.Option("ru", t("countries.ru", default="Russia")),
            ],
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=AppColors.PRIMARY,
            on_select=on_change,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.PUBLIC, size=20, color=ft.Colors.WHITE),
                        width=28,
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                    ft.Column(
                        [
                            ft.Text(t("settings.direct_country", default="Direct Country"), size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                            ft.Text(t("settings.direct_country_desc", default="Bypass proxy for specific destination country"), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    self._dropdown,
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            border_radius=10,
        )

    @property
    def value(self) -> str:
        return self._dropdown.value


class AutoReconnectToggleRow(ft.Container):
    """Self-contained auto-reconnect toggle component with standardized column alignment."""

    def __init__(self, app_context, toast_callback: Callable):
        self._app_context = app_context
        self._toast_callback = toast_callback
        is_enabled = app_context.settings.get_auto_reconnect_enabled()
        self._switch = ft.Switch(value=is_enabled, active_color=AppColors.PRIMARY, on_change=self._handle_toggle)

        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.AUTORENEW, size=20, color=ft.Colors.WHITE),
                        width=28,
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                    ft.Column(
                        [
                            ft.Text(t("settings.auto_reconnect", default="Auto Reconnect"), size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                            ft.Text(t("settings.auto_reconnect_desc", default="Automatically reconnect if session drops"), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    self._switch,
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            border_radius=10,
        )

    def _handle_toggle(self, e):
        enabled = self._switch.value
        self._app_context.settings.set_auto_reconnect_enabled(enabled)
        key = "settings.auto_reconnect_enabled" if enabled else "settings.auto_reconnect_disabled"
        self._toast_callback(t(key), "success" if enabled else "info")
        if self.page:
            self.page.update()
