"""Left Navigation Sidebar Component with Clean Empty Top (Apple macOS style) & Quick-Action Card."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors


class NavSidebar(ft.Container):
    """Sidebar navigation drawer matching Fluent Integrated design specs (image_54.png)."""

    def __init__(
        self,
        active_tab: str,
        on_tab_change: Callable[[str], None],
        on_connect_click: Callable,
        on_change_server_click: Callable | None = None,
    ):
        self._active_tab = active_tab
        self._on_tab_change = on_tab_change
        self._on_connect_click = on_connect_click
        self._on_change_server_click = on_change_server_click

        self._nav_items = [
            (
                "dashboard",
                t("nav.dashboard", default="Dashboard"),
                ft.Icons.GRID_VIEW_ROUNDED,
            ),
            (
                "statistics",
                t("nav.statistics", default="Statistics"),
                ft.Icons.BAR_CHART_ROUNDED,
            ),
            ("servers", t("nav.servers", default="Servers"), ft.Icons.DNS_ROUNDED),
            ("logs", t("nav.logs", default="Logs"), ft.Icons.TERMINAL_ROUNDED),
            (
                "settings",
                t("nav.settings", default="Settings"),
                ft.Icons.SETTINGS_ROUNDED,
            ),
        ]

        self._buttons_container = ft.Column(spacing=8, expand=True)
        self._build_nav_buttons()

        self._change_server_btn = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.SWAP_HORIZ_ROUNDED, size=16, color=ft.Colors.WHITE
                    ),
                    ft.Text(
                        t("dashboard.change_server", default="Change Server"),
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.WHITE,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=ft.Padding.symmetric(vertical=10, horizontal=14),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.12, "#a855f7"),
            border=ft.Border.all(1.2, ft.Colors.with_opacity(0.6, "#a855f7")),
            on_click=self._handle_change_server_click,
            ink=True,
        )

        self._quick_action_icon = ft.Icon(ft.Icons.BOLT, size=16, color="#f43f5e")
        self._quick_action_text = ft.Text(
            t("dashboard.quick_disconnect", default="Quick Disconnect"),
            size=12,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.WHITE,
        )

        self._quick_action_btn = ft.Container(
            content=ft.Row(
                [
                    self._quick_action_icon,
                    self._quick_action_text,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
            ),
            padding=ft.Padding.symmetric(vertical=10, horizontal=14),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.15, "#f43f5e"),
            border=ft.Border.all(1.2, ft.Colors.with_opacity(0.6, "#f43f5e")),
            on_click=self._on_connect_click,
            ink=True,
        )

        self._actions_panel = ft.Column(
            [
                self._change_server_btn,
                self._quick_action_btn,
            ],
            spacing=8,
        )

        super().__init__(
            content=ft.Column(
                [
                    ft.WindowDragArea(
                        content=ft.Container(
                            content=ft.Row(
                                [
                                    ft.Image(
                                        src="icon.png",
                                        width=22,
                                        height=22,
                                        fit="contain",
                                    ),
                                    ft.Text(
                                        "XenRay",
                                        size=15,
                                        weight=ft.FontWeight.W_800,
                                        color=ft.Colors.WHITE,
                                    ),
                                ],
                                spacing=8,
                            ),
                            padding=ft.Padding.only(left=8, top=12, bottom=16),
                        )
                    ),
                    self._buttons_container,
                    self._actions_panel,
                ],
                spacing=0,
                expand=True,
            ),
            width=210,
            padding=14,
            bgcolor=ft.Colors.with_opacity(0.4, "#0b0518"),
            border=ft.Border.only(
                right=ft.BorderSide(1, ft.Colors.with_opacity(0.12, "#a855f7"))
            ),
        )

    def _handle_change_server_click(self, e):
        if self._on_change_server_click:
            self._on_change_server_click(e)

    def set_active_tab(self, tab_id: str):
        """Set the current active navigation tab (in-place style update, no rebuild)."""
        if self._active_tab == tab_id:
            return
        self._active_tab = tab_id
        self._apply_active_styles()
        try:
            if self.page:
                self._buttons_container.update()
        except Exception:
            pass

    def update_connect_button_text(
        self, text: str, is_running: bool, server_name: str = ""
    ):
        """Update the bottom quick action button state matching connected / disconnected status."""
        btn_text = (
            t("dashboard.quick_disconnect", default="Quick Disconnect")
            if is_running
            else t("dashboard.quick_connect", default="Quick Connect")
        )
        self._quick_action_text.value = btn_text
        if is_running:
            self._quick_action_icon.color = "#f43f5e"
            self._quick_action_btn.bgcolor = ft.Colors.with_opacity(0.15, "#f43f5e")
            self._quick_action_btn.border = ft.Border.all(
                1.2, ft.Colors.with_opacity(0.6, "#f43f5e")
            )
        else:
            self._quick_action_icon.color = "#c084fc"
            self._quick_action_btn.bgcolor = ft.Colors.with_opacity(0.12, "#a855f7")
            self._quick_action_btn.border = ft.Border.all(
                1.2, ft.Colors.with_opacity(0.5, "#a855f7")
            )

        try:
            if self._quick_action_btn.page:
                self._quick_action_btn.update()
        except Exception:
            pass

    def _build_nav_buttons(self):
        """Build nav buttons once and store references for in-place updates."""
        self._buttons_container.controls.clear()
        self._button_refs: dict[str, tuple[ft.Container, ft.Icon, ft.Text]] = {}
        for tab_id, label, icon in self._nav_items:
            is_active = tab_id == self._active_tab
            icon_ctrl = ft.Icon(
                icon,
                size=18,
                color="#c084fc" if is_active else AppColors.ON_SURFACE_VARIANT,
            )
            text_ctrl = ft.Text(
                label,
                size=13,
                weight=ft.FontWeight.W_700 if is_active else ft.FontWeight.W_500,
                color=ft.Colors.WHITE if is_active else AppColors.ON_SURFACE_VARIANT,
            )
            btn = ft.Container(
                content=ft.Row(
                    [icon_ctrl, text_ctrl],
                    spacing=12,
                ),
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                border_radius=12,
                bgcolor=ft.Colors.with_opacity(0.2, "#6d28d9")
                if is_active
                else ft.Colors.TRANSPARENT,
                border=ft.Border.all(1.2, ft.Colors.with_opacity(0.5, "#a855f7"))
                if is_active
                else None,
                shadow=ft.BoxShadow(
                    spread_radius=0,
                    blur_radius=12,
                    color=ft.Colors.with_opacity(0.3, "#7c3aed"),
                    offset=ft.Offset(0, 0),
                )
                if is_active
                else None,
                on_click=lambda e, tid=tab_id: self._on_tab_change(tid),
            )
            self._button_refs[tab_id] = (btn, icon_ctrl, text_ctrl)
            self._buttons_container.controls.append(btn)

    def _apply_active_styles(self):
        """Update existing button styles in-place without rebuilding controls."""
        for tab_id, (btn, icon_ctrl, text_ctrl) in self._button_refs.items():
            is_active = tab_id == self._active_tab
            icon_ctrl.color = "#c084fc" if is_active else AppColors.ON_SURFACE_VARIANT
            text_ctrl.weight = (
                ft.FontWeight.W_700 if is_active else ft.FontWeight.W_500
            )
            text_ctrl.color = (
                ft.Colors.WHITE if is_active else AppColors.ON_SURFACE_VARIANT
            )
            btn.bgcolor = (
                ft.Colors.with_opacity(0.2, "#6d28d9")
                if is_active
                else ft.Colors.TRANSPARENT
            )
            btn.border = (
                ft.Border.all(1.2, ft.Colors.with_opacity(0.5, "#a855f7"))
                if is_active
                else None
            )
            btn.shadow = (
                ft.BoxShadow(
                    spread_radius=0,
                    blur_radius=12,
                    color=ft.Colors.with_opacity(0.3, "#7c3aed"),
                    offset=ft.Offset(0, 0),
                )
                if is_active
                else None
            )

