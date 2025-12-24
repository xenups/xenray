"""Reusable settings section components with i18n support."""
from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import t


class SettingsSection(ft.Container):
    """Base class for a settings section with a title."""

    def __init__(self, title: str, controls: list, padding_horizontal: int = 20):
        super().__init__(
            content=ft.Column(
                [
                    ft.Text(
                        title,
                        color=ft.Colors.WHITE,
                        weight=ft.FontWeight.BOLD,
                        size=12,
                    ),
                    ft.Container(height=5),
                    *controls,
                ]
            ),
            padding=ft.padding.symmetric(horizontal=padding_horizontal),
        )


class SettingsRow(ft.Container):
    """A row in a settings section with icon, label, and control."""

    def __init__(
        self,
        icon: str,
        label: str,
        control: ft.Control,
        sublabel: Optional[str] = None,
        sublabel_control: Optional[ft.Control] = None,
    ):
        label_column = ft.Column(
            [
                ft.Text(label, weight=ft.FontWeight.W_500),
            ],
            spacing=2,
            expand=True,
        )

        # Support either static sublabel text or dynamic sublabel control
        if sublabel_control:
            label_column.controls.append(sublabel_control)
        elif sublabel:
            label_column.controls.append(ft.Text(sublabel, size=11, color=ft.Colors.ON_SURFACE_VARIANT))

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(icon, color=ft.Colors.ON_SURFACE_VARIANT),
                    label_column,
                    control,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=10,
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        )


class SettingsListTile(ft.ListTile):
    """A styled list tile for settings navigation."""

    def __init__(
        self,
        icon: str,
        title: str,
        subtitle: str,
        on_click: Optional[Callable] = None,
        show_chevron: bool = True,
    ):
        trailing = ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=ft.Colors.OUTLINE) if show_chevron else None

        super().__init__(
            leading=ft.Icon(icon, color=ft.Colors.ON_SURFACE_VARIANT),
            title=ft.Text(title, weight=ft.FontWeight.W_500),
            subtitle=ft.Text(subtitle, size=12),
            trailing=trailing,
            on_click=on_click,
            shape=ft.RoundedRectangleBorder(radius=8),
        )


class ModeSwitchRow(ft.Container):
    """Mode switch row (VPN/Proxy) for settings."""

    def __init__(self, is_proxy: bool, on_change: Callable):
        self._switch = ft.Switch(
            value=is_proxy,
            active_color=ft.Colors.PRIMARY,
            on_change=on_change,
        )
        self._is_proxy = is_proxy

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.VPN_LOCK, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column(
                        [
                            ft.Text(
                                t("settings.connection_mode"),
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                t("settings.mode_description"),
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Row(
                        [
                            ft.Text(
                                t("settings.vpn"),
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                weight=ft.FontWeight.BOLD if not is_proxy else ft.FontWeight.NORMAL,
                            ),
                            self._switch,
                            ft.Text(
                                t("settings.proxy"),
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                weight=ft.FontWeight.BOLD if is_proxy else ft.FontWeight.NORMAL,
                            ),
                        ],
                        spacing=5,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=10,
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        )

    @property
    def value(self) -> bool:
        return self._switch.value

    @value.setter
    def value(self, val: bool):
        self._switch.value = val


class PortInputRow(ft.Container):
    """Port input row for settings."""

    def __init__(self, initial_value: int, on_save: Callable):
        self._field = ft.TextField(
            value=str(initial_value),
            width=100,
            height=40,
            text_size=14,
            content_padding=8,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.CENTER,
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.INPUT, size=24, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(
                        t("settings.socks_port"),
                        size=12,
                        weight=ft.FontWeight.W_500,
                        width=80,
                    ),
                    self._field,
                    ft.IconButton(
                        icon=ft.Icons.CHECK,
                        icon_size=20,
                        icon_color=ft.Colors.PRIMARY,
                        tooltip=t("settings.save"),
                        on_click=lambda e: on_save(self._field.value),
                    ),
                ],
                spacing=5,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
        )

    @property
    def value(self) -> str:
        return self._field.value

    def set_border_color(self, color):
        self._field.border_color = color
        self._field.update()


class CountryDropdownRow(ft.Container):
    """Country dropdown row for direct routing settings."""

    def __init__(self, current_value: str, on_change: Callable):
        self._dropdown = ft.Dropdown(
            width=120,
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
            on_change=on_change,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.PUBLIC, size=24, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(
                        t("settings.direct_country"),
                        size=12,
                        weight=ft.FontWeight.W_500,
                        width=80,
                    ),
                    self._dropdown,
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=8, vertical=8),
        )

    @property
    def value(self) -> str:
        return self._dropdown.value


class LanguageDropdownRow(ft.Container):
    """Language dropdown row with flag images."""

    def __init__(self, current_value: str, on_change: Callable):
        # Language options with flag codes
        self._languages = [
            ("en", "gb", "English"),
            ("fa", "ir", "فارسی"),
            ("zh", "cn", "中文"),
            ("ru", "ru", "Русский"),
        ]

        self._dropdown = ft.Dropdown(
            width=160,
            text_size=12,
            content_padding=8,
            value=current_value if current_value else "en",
            options=[ft.dropdown.Option(lang_code, f"{name}") for lang_code, flag_code, name in self._languages],
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
            on_change=on_change,
        )

        # Get current flag code
        current_flag = "gb"
        for lang_code, flag_code, name in self._languages:
            if lang_code == (current_value or "en"):
                current_flag = flag_code
                break

        self._flag_image = ft.Image(
            src=f"/flags/{current_flag}.svg",
            width=24,
            height=18,
            fit=ft.ImageFit.COVER,
            border_radius=3,
            filter_quality=ft.FilterQuality.HIGH,
            anti_alias=True,
        )

        # Update flag when language changes
        original_on_change = on_change

        def wrapped_on_change(e):
            selected = self._dropdown.value
            for lang_code, flag_code, name in self._languages:
                if lang_code == selected:
                    self._flag_image.src = f"/flags/{flag_code}.svg"
                    self._flag_image.update()
                    break
            original_on_change(e)

        self._dropdown.on_change = wrapped_on_change

        super().__init__(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Container(
                                content=self._flag_image,
                                alignment=ft.alignment.center,
                            ),
                            ft.Text(
                                t("settings.language"),
                                size=11,
                                weight=ft.FontWeight.W_500,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        spacing=4,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        width=60,
                    ),
                    self._dropdown,
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
        )

    @property
    def value(self) -> str:
        return self._dropdown.value
