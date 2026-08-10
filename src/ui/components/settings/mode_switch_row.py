"""Mode switch component for VPN vs. Proxy selection."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class ModeSwitchRow(ft.Container):
    """Mode switch row (VPN/Proxy) for settings."""

    def __init__(self, is_proxy: bool, on_change: Callable):
        self._switch = ft.Switch(
            value=is_proxy,
            active_color=ft.Colors.PRIMARY,
            on_change=on_change,
        )
        self._is_proxy = is_proxy
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
                            self._vpn_text,
                            self._switch,
                            self._proxy_text,
                        ],
                        spacing=5,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
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
