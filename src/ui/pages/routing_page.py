"""Routing rules management page with i18n support."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.app_context import AppContext
from src.core.i18n import t
from src.ui.components.common import PageHeader
from src.ui.components.routing import RoutingToggleRow, RuleItemRow
from src.ui.controllers.routing_controller import RoutingController


class RoutingPage(ft.Container):
    """Routing rules management page with targeted tab switching and rule list updates."""

    def __init__(self, app_context: AppContext, on_back: Callable):
        self._app_context = app_context
        self._on_back = on_back
        self._controller = RoutingController(app_context=app_context)
        self._current_tab = "quick"

        super().__init__(
            expand=True,
            padding=0,
            bgcolor=ft.Colors.with_opacity(0.3, "#0f172a"),
            blur=ft.Blur(20, 20, ft.BlurTileMode.MIRROR),
        )
        self._setup_ui()

    def _on_toggle_change(self, key: str, value: bool) -> None:
        """Handle toggle change via RoutingController."""
        self._controller.update_toggle(key, value)

    def _setup_ui(self) -> None:
        header = PageHeader(
            title=t("routing.title"),
            subtitle=t("routing.subtitle"),
            on_back=self._on_back,
        )

        self._quick_settings_view = ft.Container(
            content=ft.Column(
                [
                    RoutingToggleRow(
                        "block_udp_443",
                        t("routing.block_udp443"),
                        t("routing.block_udp443_desc"),
                        ft.Icons.BLOCK,
                        self._controller.toggles.get("block_udp_443", False),
                        self._on_toggle_change,
                    ),
                    RoutingToggleRow(
                        "block_ads",
                        t("routing.block_ads"),
                        t("routing.block_ads_desc"),
                        ft.Icons.AD_UNITS_OUTLINED,
                        self._controller.toggles.get("block_ads", False),
                        self._on_toggle_change,
                    ),
                    RoutingToggleRow(
                        "direct_private_ips",
                        t("routing.direct_private"),
                        t("routing.direct_private_desc"),
                        ft.Icons.LAN,
                        self._controller.toggles.get("direct_private_ips", False),
                        self._on_toggle_change,
                    ),
                    RoutingToggleRow(
                        "direct_local_domains",
                        t("routing.direct_local"),
                        t("routing.direct_local_desc"),
                        ft.Icons.HOME_WORK,
                        self._controller.toggles.get("direct_local_domains", False),
                        self._on_toggle_change,
                    ),
                ],
                spacing=0,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=10),
            expand=True,
        )

        tab_keys = ["direct", "proxy", "block"]
        self._rule_tabs = {}
        tab_contents: list[ft.Control] = [self._quick_settings_view]

        for tab_key in tab_keys:
            input_field = ft.TextField(
                label=t("routing.domain_or_ip"),
                hint_text=t("routing.hint"),
                expand=True,
                text_size=14,
                height=40,
                content_padding=10,
                border_radius=8,
            )
            input_field.on_submit = lambda e, k=tab_key, inp=input_field: self._add_rule(k, inp)
            add_btn = ft.ElevatedButton(
                t("routing.add"),
                icon=ft.Icons.ADD,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    color=ft.Colors.ON_PRIMARY,
                    bgcolor=ft.Colors.PRIMARY,
                    padding=ft.Padding.symmetric(horizontal=20),
                ),
                on_click=lambda e, k=tab_key, inp=input_field: self._add_rule(k, inp),
                height=40,
            )
            list_view = ft.ListView(
                expand=True,
                spacing=2,
                padding=ft.Padding.symmetric(horizontal=20, vertical=0),
            )

            self._rule_tabs[tab_key] = {"input": input_field, "list_view": list_view}

            tab_contents.append(
                ft.Column(
                    [
                        ft.Container(
                            content=ft.Row([input_field, add_btn], spacing=10),
                            padding=ft.Padding.symmetric(horizontal=20, vertical=10),
                        ),
                        ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.5),
                        list_view,
                    ],
                    spacing=0,
                    expand=True,
                )
            )

        self._tabs = ft.Tabs(
            length=4,
            selected_index=0,
            animation_duration=300,
            on_change=self._on_tab_change,
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label=t("routing.quick_settings"), icon=ft.Icons.TUNE),
                            ft.Tab(label=t("routing.direct"), icon=ft.Icons.DIRECTIONS),
                            ft.Tab(label=t("routing.proxy"), icon=ft.Icons.VPN_LOCK),
                            ft.Tab(label=t("routing.block"), icon=ft.Icons.BLOCK),
                        ],
                        divider_color=ft.Colors.TRANSPARENT,
                        indicator_color=ft.Colors.PRIMARY,
                        label_color=ft.Colors.PRIMARY,
                        unselected_label_color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.TabBarView(expand=True, controls=tab_contents),
                ],
            ),
        )

        self.content = ft.Column([header, self._tabs], spacing=0)

    def _on_tab_change(self, e) -> None:
        idx = self._tabs.selected_index
        tab_map = {0: "quick", 1: "direct", 2: "proxy", 3: "block"}
        self._current_tab = tab_map.get(idx, "quick")
        if idx > 0:
            self._refresh_list(self._current_tab, update=True)

    def _refresh_list(self, tab_key: str, update: bool = True) -> None:
        list_view = self._rule_tabs[tab_key]["list_view"]
        list_view.controls.clear()
        items = self._controller.rules.get(tab_key, [])

        if not items:
            tab_name = t(f"routing.{tab_key}")
            list_view.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.LIST_ALT, size=48, color=ft.Colors.OUTLINE_VARIANT),
                            ft.Text(t("routing.no_rules", type=tab_name), color=ft.Colors.ON_SURFACE_VARIANT),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=50,
                    opacity=0.5,
                )
            )

        for item in items:
            list_view.controls.append(RuleItemRow(item=item, on_delete=self._delete_rule))

        if update and self.page:
            list_view.update()

    def _add_rule(self, tab_key: str, input_field: ft.TextField) -> None:
        val = input_field.value.strip()
        if self._controller.add_rule(tab_key, val):
            self._refresh_list(tab_key, update=True)

        input_field.value = ""
        input_field.focus()
        input_field.update()

    def _delete_rule(self, item: str) -> None:
        if self._controller.delete_rule(self._current_tab, item):
            self._refresh_list(self._current_tab, update=True)
