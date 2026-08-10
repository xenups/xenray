"""Servers View Component."""

from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from src.core.country_translator import translate_country
from src.core.i18n import t
from src.ui.helpers.gradient_helper import GradientHelper
from src.ui.theme import AppColors, create_glass_container


class ServersView(ft.Container):
    """Available Nodes & Servers management view based on Stitch specs."""

    def __init__(
        self,
        server_list_component: ft.Control,
        on_search_change: Callable[[str], None],
        on_add_server_click: Callable,
    ):
        self._server_list_component = server_list_component
        self._on_search_change = on_search_change
        self._on_add_server_click = on_add_server_click

        self._search_field = ft.TextField(
            hint_text=t(
                "servers.search_placeholder",
                default="Search server name, region or IP...",
            ),
            prefix_icon=ft.Icons.SEARCH,
            border_radius=24,
            height=44,
            text_style=ft.TextStyle(color=ft.Colors.WHITE),
            content_padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            border_color=AppColors.GLASS_BORDER,
            focused_border_color=AppColors.PRIMARY,
            on_change=lambda e: self._on_search_change(e.control.value),
            expand=True,
        )

        self._hero_badge = ft.Container(
            content=ft.Text(
                t("servers.selected_node", default="SELECTED NODE"),
                size=10,
                weight=ft.FontWeight.W_700,
                color=AppColors.PRIMARY,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
        )
        self._hero_node_name = ft.Text(
            "--", size=18, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE
        )
        self._hero_node_protocol = ft.Text("--", size=11, color=ft.Colors.WHITE)
        self._hero_node_speed = ft.Text("--", size=11, color=ft.Colors.WHITE)
        self._hero_node_latency = ft.Text(
            "--", size=22, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE
        )
        self._hero_flag = ft.Image(src="", width=28, height=20, visible=False)

        self._hero_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            self._hero_badge,
                            ft.Icon(
                                ft.Icons.VERIFIED, size=18, color=AppColors.SECONDARY
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row(
                        [
                            ft.Container(
                                content=self._hero_flag,
                                width=48,
                                height=36,
                                border_radius=10,
                                alignment=ft.Alignment.CENTER,
                                bgcolor=AppColors.SURFACE_CONTAINER_HIGH,
                            ),
                            ft.Column(
                                [
                                    self._hero_node_name,
                                    ft.Row(
                                        [
                                            ft.Icon(
                                                ft.Icons.WIFI,
                                                size=14,
                                                color=ft.Colors.WHITE,
                                            ),
                                            self._hero_node_protocol,
                                            ft.Icon(
                                                ft.Icons.LAN,
                                                size=14,
                                                color=ft.Colors.WHITE,
                                            ),
                                            self._hero_node_speed,
                                        ],
                                        spacing=6,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Column(
                                [
                                    self._hero_node_latency,
                                    ft.Text(
                                        t("servers.latency", default="LATENCY"),
                                        size=9,
                                        weight=ft.FontWeight.W_700,
                                        color=AppColors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                            ),
                        ],
                        spacing=16,
                    ),
                ],
                spacing=12,
            ),
            padding=16,
            border_radius=16,
        )

        super().__init__(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            self._search_field,
                            ft.ElevatedButton(
                                content=ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.ADD, size=18, color=ft.Colors.WHITE
                                        ),
                                        ft.Text(
                                            t("servers.add", default="Add Server"),
                                            size=13,
                                            color=ft.Colors.WHITE,
                                            weight=ft.FontWeight.W_600,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=6,
                                ),
                                style=ft.ButtonStyle(
                                    bgcolor=AppColors.PRIMARY,
                                    color=ft.Colors.WHITE,
                                    shape=ft.RoundedRectangleBorder(radius=22),
                                    padding=ft.Padding.symmetric(
                                        horizontal=18, vertical=10
                                    ),
                                ),
                                height=44,
                                on_click=self._on_add_server_click,
                            ),
                        ],
                        spacing=12,
                    ),
                    ft.Container(
                        content=self._server_list_component,
                        expand=True,
                    ),
                ],
                spacing=12,
                expand=True,
            ),
            padding=14,
            expand=True,
        )

    def update_hero_node(
        self,
        name: str,
        latency: str,
        protocol: str = "",
        speed: str = "",
        country_code: str = "",
    ):
        """Update top featured node info (noop after SELECTED NODE banner removal)."""
        pass
