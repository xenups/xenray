"""Settings View Component matching Slate Dark & Electric Cyan design specs."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import is_rtl, t
from src.ui.components.settings_sections import (
    AutoReconnectToggleRow,
    CountryDropdownRow,
    LanShareToggleRow,
    LanguageDropdownRow,
    ModeSwitchRow,
    PortInputRow,
    SettingsListTile,
    StartupToggleRow,
    TunEngineRow,
)
from src.ui.theme import AppColors, create_glass_container


class SettingsView(ft.Container):
    """Modern Bento Grid Settings View based on Stitch specs."""

    def __init__(
        self,
        mode_switch_row: ModeSwitchRow,
        tun_engine_row: TunEngineRow,
        port_row: PortInputRow,
        country_row: CountryDropdownRow,
        language_row: LanguageDropdownRow,
        reconnect_row: AutoReconnectToggleRow,
        startup_row: StartupToggleRow,
        on_check_update_click: Callable,
        on_open_routing_click: Optional[Callable] = None,
        on_open_dns_click: Optional[Callable] = None,
        lan_share_row: Optional[LanShareToggleRow] = None,
        routing_badge_text: str = "12 Active Rules",
        dns_badge_text: str = "Cloudflare (1.1.1.1)",
    ):
        self._mode_switch_row = mode_switch_row
        self._tun_engine_row = tun_engine_row
        self._port_row = port_row
        self._country_row = country_row
        self._language_row = language_row
        self._reconnect_row = reconnect_row
        self._startup_row = startup_row
        self._lan_share_row = lan_share_row
        self._on_check_update_click = on_check_update_click
        self._on_open_routing_click = on_open_routing_click
        self._on_open_dns_click = on_open_dns_click

        WHITE = ft.Colors.WHITE

        connectivity_controls = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(
                                ft.Icons.WIFI_TETHERING,
                                color=AppColors.PRIMARY,
                                size=22,
                            ),
                            width=28,
                            alignment=ft.Alignment.CENTER_LEFT,
                        ),
                        ft.Text(
                            t(
                                "settings.connectivity_title",
                                default="Connectivity Settings",
                            ),
                            size=16,
                            weight=ft.FontWeight.W_700,
                            color=WHITE,
                        ),
                    ],
                    spacing=12,
                ),
                padding=ft.Padding.only(left=8, right=8, top=4, bottom=10),
                border=ft.Border.only(
                    bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.12, WHITE))
                ),
            ),
            self._mode_switch_row,
            self._tun_engine_row,
            self._port_row,
        ]

        if self._lan_share_row:
            connectivity_controls.append(self._lan_share_row)

        self._connectivity_card = create_glass_container(
            content=ft.Column(
                connectivity_controls,
                spacing=10,
            ),
        )

        routing_controls = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(
                                ft.Icons.ALT_ROUTE, color=AppColors.PRIMARY, size=22
                            ),
                            width=28,
                            alignment=ft.Alignment.CENTER_LEFT,
                        ),
                        ft.Text(
                            t("settings.routing_title", default="Routing & Anti-Leak"),
                            size=16,
                            weight=ft.FontWeight.W_700,
                            color=WHITE,
                        ),
                    ],
                    spacing=12,
                ),
                padding=ft.Padding.only(left=8, right=8, top=4, bottom=10),
                border=ft.Border.only(
                    bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.12, WHITE))
                ),
            ),
            self._country_row,
        ]

        if self._on_open_routing_click:
            routing_controls.append(
                SettingsListTile(
                    ft.Icons.ROUTE,
                    t("settings.routing_rules", default="Custom Routing Rules"),
                    t(
                        "settings.routing_description",
                        default="Configure custom domain and IP routing rules",
                    ),
                    on_click=self._on_open_routing_click,
                    badge_text=routing_badge_text,
                )
            )

        if self._on_open_dns_click:
            routing_controls.append(
                SettingsListTile(
                    ft.Icons.DNS,
                    t("settings.dns_manager", default="DNS Management"),
                    t(
                        "settings.dns_description",
                        default="Configure custom DNS servers and resolution strategies",
                    ),
                    on_click=self._on_open_dns_click,
                    badge_text=dns_badge_text,
                )
            )

        self._routing_card = create_glass_container(
            content=ft.Column(
                routing_controls,
                spacing=10,
            ),
        )

        self._preferences_card = create_glass_container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(
                                        ft.Icons.TUNE, color=AppColors.PRIMARY, size=22
                                    ),
                                    width=28,
                                    alignment=ft.Alignment.CENTER_LEFT,
                                ),
                                ft.Text(
                                    t(
                                        "settings.preferences_title",
                                        default="Application Preferences",
                                    ),
                                    size=16,
                                    weight=ft.FontWeight.W_700,
                                    color=WHITE,
                                ),
                            ],
                            spacing=12,
                        ),
                        padding=ft.Padding.only(left=8, right=8, top=4, bottom=10),
                        border=ft.Border.only(
                            bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.12, WHITE))
                        ),
                    ),
                    self._language_row,
                    self._reconnect_row,
                    self._startup_row,
                ],
                spacing=10,
            ),
        )

        self._update_card = create_glass_container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                "XenRay Client",
                                size=14,
                                weight=ft.FontWeight.W_700,
                                color=WHITE,
                            ),
                            ft.Text(
                                t("settings.version", default="v1.0.0"),
                                size=12,
                                color=AppColors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                    ),
                    ft.ElevatedButton(
                        content=ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.SYSTEM_UPDATE_ALT, size=15, color=WHITE
                                ),
                                ft.Text(
                                    t(
                                        "settings.check_updates",
                                        default="Check for Updates",
                                    ),
                                    size=12,
                                    color=AppColors.ON_PRIMARY,
                                    weight=ft.FontWeight.W_600,
                                ),
                            ],
                            spacing=6,
                        ),
                        style=ft.ButtonStyle(
                            bgcolor=AppColors.PRIMARY,
                            color=AppColors.ON_PRIMARY,
                            shape=ft.RoundedRectangleBorder(radius=8),
                            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                        ),
                        on_click=self._on_check_update_click,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

        super().__init__(
            content=ft.Column(
                [
                    self._connectivity_card,
                    self._routing_card,
                    self._preferences_card,
                    self._update_card,
                ],
                spacing=14,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            padding=ft.Padding.only(left=20, right=20, top=20, bottom=40),
            expand=True,
        )
