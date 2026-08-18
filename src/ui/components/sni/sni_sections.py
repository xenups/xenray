"""SNI Spoof page sections — reusable target / relay / settings-card components.

Each section is a self-contained ``ft.Container``/``ft.Column`` that owns its
layout and receives the field callbacks from the page (the orchestrator).
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.components.sni.sni_field_row import SniFieldRow


class SniSectionHeader(ft.Row):
    """A compact section title with an icon (Target & Spoofing / Local Relay)."""

    def __init__(self, icon: ft.Icons, label_key: str, label_default: str):
        super().__init__(
            [
                ft.Icon(icon, size=16, color="#A78BFA"),
                ft.Text(
                    t(label_key, default=label_default),
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.WHITE,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )


class SniTargetSection(ft.Column):
    """Target & Spoofing section: Disguise SNI, Connect IP, Connect Port."""

    def __init__(
        self,
        *,
        fake_sni: str,
        connect_ip: str,
        connect_port: str,
        on_fake_sni_change: Callable,
        on_connect_ip_change: Callable,
        on_connect_port_change: Callable,
    ):
        self.fake_sni_field = SniFieldRow(
            initial_value=fake_sni,
            on_change=on_fake_sni_change,
            label_key="sni_spoof.fake_sni",
            label_default="Disguise SNI (Fake SNI)",
            hint_default="chatgpt.com",
            icon=ft.Icons.LANGUAGE_ROUNDED,
        )
        self.connect_ip_field = SniFieldRow(
            initial_value=connect_ip,
            on_change=on_connect_ip_change,
            label_key="sni_spoof.connect_ip",
            label_default="Connect IP",
            hint_default="185.193.30.94",
            icon=ft.Icons.DNS_ROUNDED,
        )
        self.connect_port_field = SniFieldRow(
            initial_value=connect_port,
            on_change=on_connect_port_change,
            label_key="sni_spoof.connect_port",
            label_default="Connect Port",
            hint_default="443",
            icon=ft.Icons.TAG_ROUNDED,
            numeric=True,
        )
        super().__init__(
            [
                SniSectionHeader(
                    ft.Icons.VPN_LOCK_ROUNDED,
                    "sni_spoof.target_section",
                    "Target & Spoofing",
                ),
                self.fake_sni_field,
                ft.Row(
                    [self.connect_ip_field, self.connect_port_field],
                    spacing=12,
                ),
            ],
            spacing=14,
        )


class SniRelaySection(ft.Column):
    """Local Relay Listener section: Listen Host, Listen Port."""

    def __init__(
        self,
        *,
        listen_host: str,
        listen_port: str,
        on_listen_host_change: Callable,
        on_listen_port_change: Callable,
    ):
        self.listen_host_field = SniFieldRow(
            initial_value=listen_host,
            on_change=on_listen_host_change,
            label_key="sni_spoof.listen_host",
            label_default="Listen Host",
            hint_default="127.0.0.1",
            icon=ft.Icons.COMPUTER_ROUNDED,
        )
        self.listen_port_field = SniFieldRow(
            initial_value=listen_port,
            on_change=on_listen_port_change,
            label_key="sni_spoof.listen_port",
            label_default="Listen Port",
            hint_default="40443",
            icon=ft.Icons.NUMBERS_ROUNDED,
            numeric=True,
        )
        super().__init__(
            [
                SniSectionHeader(
                    ft.Icons.ROUTER_ROUNDED,
                    "sni_spoof.relay_section",
                    "Local Relay Listener",
                ),
                ft.Row(
                    [self.listen_host_field, self.listen_port_field],
                    spacing=12,
                ),
            ],
            spacing=14,
        )


class SniSettingsCard(ft.Container):
    """The unified settings card: Target section, divider, Relay section."""

    def __init__(
        self,
        *,
        target_section: SniTargetSection,
        relay_section: SniRelaySection,
    ):
        super().__init__(
            content=ft.Column(
                [
                    target_section,
                    ft.Container(
                        height=1,
                        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
                        margin=ft.Margin.symmetric(vertical=6),
                    ),
                    relay_section,
                ],
                spacing=14,
            ),
            padding=ft.Padding.all(18),
            border_radius=14,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.07, ft.Colors.WHITE)),
            bgcolor="#121620",
        )
