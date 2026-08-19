"""Servers Page Component."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.ui.components.servers.server_search_bar import ServerSearchBar
from src.ui.theme import GlassTokens


class ServersPage(ft.Container):
    """Available Nodes & Servers management page based on Stitch specs."""

    def __init__(
        self,
        server_list_component: ft.Control,
        on_search_change: Callable[[str], None],
        on_add_server_click: Callable,
    ):
        self._server_list_component = server_list_component
        self._on_search_change = on_search_change
        self._on_add_server_click = on_add_server_click

        search_bar = ServerSearchBar(
            on_search_change=self._on_search_change,
            on_add_server_click=self._on_add_server_click,
        )

        super().__init__(
            content=ft.Column(
                [
                    search_bar,
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
            bgcolor=GlassTokens.BG_PAGE,
        )


# Backward-compatibility alias
ServersView = ServersPage
