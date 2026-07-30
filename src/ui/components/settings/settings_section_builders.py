"""Settings Section Builders - Radio cards, Engine selector rows, and card controls."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import is_rtl, t
from src.ui.theme import AppColors


def rtl_aware(expand: bool = False):
    rtl = is_rtl()
    return {"expand": expand}


class SettingsSection(ft.Container):
    """Base class for a settings section with a title."""

    def __init__(self, title: str, controls: list, padding_horizontal: int = 20):
        rtl = is_rtl()
        super().__init__(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Text(
                            title,
                            color=ft.Colors.WHITE,
                            weight=ft.FontWeight.BOLD,
                            size=18,
                        ),
                        alignment=ft.Alignment(1.0 if rtl else -1.0, 0),
                        padding=ft.Padding.only(bottom=8),
                        border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.12, ft.Colors.WHITE))),
                    ),
                    ft.Container(height=8),
                    *controls,
                ],
            ),
            padding=ft.Padding.symmetric(horizontal=padding_horizontal),
        )


class ModeRadioCards(ft.Container):
    """Connection mode selector using radio cards (TUN/VPN vs System Proxy)."""

    def __init__(self, is_proxy: bool, on_change: Callable):
        self._on_change = on_change
        self._is_proxy = is_proxy
        rtl = is_rtl()
        PURPLE = AppColors.PRIMARY
        PURPLE_SEC = AppColors.SECONDARY

        self._vpn_card = self._build_card(
            icon=ft.Icons.VPN_LOCK,
            label=t("settings.vpn_mode"),
            desc=t("settings.vpn_mode_desc"),
            badge=t("settings.recommended"),
            value=True,
            selected=not is_proxy,
            accent=PURPLE,
            rtl=rtl,
        )
        self._proxy_card = self._build_card(
            icon=ft.Icons.WIFI,
            label=t("settings.proxy_mode"),
            desc=t("settings.proxy_mode_desc"),
            badge=None,
            value=False,
            selected=is_proxy,
            accent=PURPLE_SEC,
            rtl=rtl,
        )

        super().__init__(
            content=ft.Column(
                [
                    ft.Row(
                        [self._vpn_card, self._proxy_card],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                spacing=6,
            ),
            padding=4,
        )

    def _build_card(self, icon, label, desc, badge, value, selected, accent: str, rtl: bool):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(icon, size=24, color=ft.Colors.WHITE),
                    ft.Text(
                        label,
                        size=12,
                        weight=ft.FontWeight.W_700,
                        color=ft.Colors.WHITE,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(desc, size=10, color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER),
                    ft.Container(
                        content=ft.Text(badge, size=9, weight=ft.FontWeight.W_700, color=accent)
                        if badge
                        else ft.Container(height=0),
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                        border_radius=8,
                        bgcolor=ft.Colors.with_opacity(0.12, accent) if badge else None,
                        visible=badge is not None,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            width=140,
            height=110,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.15, accent) if selected else ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            border=ft.Border.all(1.5, accent)
            if selected
            else ft.Border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.WHITE)),
            padding=10,
            on_click=lambda e: self._handle_select(value),
            ink=False,
        )

    def _handle_select(self, is_proxy: bool):
        self._is_proxy = is_proxy
        self._on_change(is_proxy)

    @property
    def value(self) -> bool:
        return self._is_proxy


class ModeSwitchRow(ft.Container):
    """Original mode switch row with standardized column alignment."""

    def __init__(self, is_proxy: bool, on_change: Callable):
        self._is_proxy = is_proxy
        self._switch = ft.Switch(value=is_proxy, active_color=AppColors.PRIMARY, on_change=on_change)
        self._vpn_text = ft.Text(
            t("settings.vpn"),
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
            weight=ft.FontWeight.BOLD if not is_proxy else ft.FontWeight.NORMAL,
        )
        self._proxy_text = ft.Text(
            t("settings.proxy"),
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
            weight=ft.FontWeight.BOLD if is_proxy else ft.FontWeight.NORMAL,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.VPN_LOCK, size=20, color=ft.Colors.WHITE),
                        width=28,
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                    ft.Column(
                        [
                            ft.Text(t("settings.connection_mode", default="Connection Mode"), size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                            ft.Text(t("settings.mode_description", default="Toggle between TUN/VPN and System Proxy"), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Row([self._vpn_text, self._switch, self._proxy_text], spacing=4),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            border_radius=10,
        )

    @property
    def value(self) -> bool:
        return self._switch.value

    @value.setter
    def value(self, val: bool):
        self._switch.value = val
        self._is_proxy = val
        self._vpn_text.weight = ft.FontWeight.BOLD if not val else ft.FontWeight.NORMAL
        self._proxy_text.weight = ft.FontWeight.BOLD if val else ft.FontWeight.NORMAL
        try:
            self._vpn_text.update()
            self._proxy_text.update()
            self._switch.update()
        except RuntimeError:
            pass


class TunEngineRow(ft.Container):
    """TUN engine selector row with standardized column alignment."""

    def __init__(self, current_engine: str, on_change: Callable):
        self._dropdown = ft.Dropdown(
            width=140,
            height=38,
            text_size=12,
            content_padding=8,
            value=current_engine if current_engine else "sing-box",
            options=[
                ft.dropdown.Option("sing-box", "✦ sing-box"),
                ft.dropdown.Option("xray", "◈ Xray"),
            ],
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=AppColors.PRIMARY,
            on_select=on_change,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.SETTINGS_ETHERNET, size=20, color=ft.Colors.WHITE),
                        width=28,
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                    ft.Column(
                        [
                            ft.Text(t("settings.tun_engine", default="TUN Engine"), size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                            ft.Text(t("settings.tun_engine_hint", default="Core driver engine for VPN TUN mode"), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
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


class LanguageDropdownRow(ft.Container):
    """Language dropdown row with standardized column alignment."""

    def __init__(self, current_value: str, on_change: Callable):
        self._on_change = on_change
        self._languages = [
            ("en", "gb", "English"),
            ("fa", "ir", "فارسی"),
            ("zh", "cn", "中文"),
            ("ru", "ru", "Русский"),
        ]

        current_flag = "gb"
        for lang_code, flag_code, name in self._languages:
            if lang_code == (current_value or "en"):
                current_flag = flag_code
                break

        self._flag_image = ft.Image(
            src=f"/flags/{current_flag}.svg",
            width=22,
            height=16,
            border_radius=3,
        )

        self._dropdown = ft.Dropdown(
            width=140,
            height=38,
            text_size=12,
            content_padding=8,
            value=current_value if current_value else "en",
            options=[ft.dropdown.Option(lang_code, f"{name}") for lang_code, flag_code, name in self._languages],
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=AppColors.PRIMARY,
            on_select=self._handle_change,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        content=self._flag_image,
                        width=28,
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                    ft.Column(
                        [
                            ft.Text(t("settings.language", default="Application Language"), size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                            ft.Text(t("settings.language_desc", default="Interface display language"), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
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

    def _handle_change(self, e):
        selected = self._dropdown.value
        for lang_code, flag_code, name in self._languages:
            if lang_code == selected:
                self._flag_image.src = f"/flags/{flag_code}.svg"
                try:
                    self._flag_image.update()
                except Exception:
                    pass
                break
        if self._on_change:
            self._on_change(selected)

    @property
    def value(self) -> str:
        return self._dropdown.value


class StartupToggleRow(ft.Container):
    """Self-contained startup toggle component with standardized column alignment."""

    def __init__(
        self,
        app_context,
        is_registered: bool,
        is_supported: bool,
        on_register: Callable,
        on_unregister: Callable,
        toast_callback: Callable,
    ):
        self._app_context = app_context
        self._on_register = on_register
        self._on_unregister = on_unregister
        self._toast_callback = toast_callback
        self._switch = ft.Switch(
            value=is_registered,
            active_color=AppColors.PRIMARY,
            on_change=self._handle_toggle,
            disabled=not is_supported,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.ROCKET_LAUNCH, size=20, color=ft.Colors.WHITE),
                        width=28,
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                    ft.Column(
                        [
                            ft.Text(t("settings.add_to_startup", default="Start on System Boot"), size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                            ft.Text(t("settings.add_to_startup_desc", default="Launch application automatically at startup"), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
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
        fn = self._on_register if enabled else self._on_unregister
        success, msg = fn()
        if success:
            self._app_context.settings.set_startup_enabled(enabled)
            self._toast_callback(t("settings.startup_saved"), "success")
        else:
            self._switch.value = not enabled
            self._switch.update()
            self._toast_callback(t("settings.startup_error"), "error")
        if self.page:
            self.page.update()
