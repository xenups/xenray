"""SNI Spoof page sections — Apple-style clean target / relay / settings-card components."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import t
from src.ui.components.sni.sni_field_row import SniFieldRow


class SniSectionHeader(ft.Row):
    """A minimal group section title."""

    def __init__(self, icon: Optional[ft.Icons], label_key: str, label_default: str):
        super().__init__(
            [
                ft.Text(
                    t(label_key, default=label_default).upper(),
                    size=10,
                    weight=ft.FontWeight.W_400,
                    style=ft.TextStyle(letter_spacing=0.8),
                    color=ft.Colors.with_opacity(0.40, ft.Colors.WHITE),
                ),
            ],
            spacing=4,
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
            label_default="Disguise SNI",
            hint_default="chatgpt.com",
        )
        self.connect_ip_field = SniFieldRow(
            initial_value=connect_ip,
            on_change=on_connect_ip_change,
            label_key="sni_spoof.connect_ip",
            label_default="Connect IP",
            hint_default="185.193.30.94",
        )
        self.connect_port_field = SniFieldRow(
            initial_value=connect_port,
            on_change=on_connect_port_change,
            label_key="sni_spoof.connect_port",
            label_default="Connect Port",
            hint_default="443",
            numeric=True,
        )
        super().__init__(
            [
                SniSectionHeader(
                    None,
                    "sni_spoof.target_section",
                    "Target & Spoofing",
                ),
                self.fake_sni_field,
                ft.Divider(height=1, color=ft.Colors.with_opacity(0.04, ft.Colors.WHITE)),
                self.connect_ip_field,
                ft.Divider(height=1, color=ft.Colors.with_opacity(0.04, ft.Colors.WHITE)),
                self.connect_port_field,
            ],
            spacing=2,
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
        )
        self.listen_port_field = SniFieldRow(
            initial_value=listen_port,
            on_change=on_listen_port_change,
            label_key="sni_spoof.listen_port",
            label_default="Listen Port",
            hint_default="40443",
            numeric=True,
        )
        super().__init__(
            [
                SniSectionHeader(
                    None,
                    "sni_spoof.relay_section",
                    "Local Relay Listener",
                ),
                self.listen_host_field,
                ft.Divider(height=1, color=ft.Colors.with_opacity(0.04, ft.Colors.WHITE)),
                self.listen_port_field,
            ],
            spacing=2,
        )


class SniSettingsCard(ft.Container):
    """The unified Apple macOS/iOS glassmorphism settings panel."""

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
                        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                        margin=ft.Margin.symmetric(vertical=4),
                    ),
                    relay_section,
                ],
                spacing=4,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            border_radius=14,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
        )
