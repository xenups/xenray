"""Left Navigation Sidebar Component - Collapsed Compact Icon-Only Navigation Rail (70px)."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors


class NavSidebar(ft.Container):
    """Compact collapsed icon-only navigation sidebar rail matching 70px width spec."""

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
                ft.Icons.DASHBOARD_ROUNDED,
            ),
            ("servers", t("nav.servers", default="Servers"), ft.Icons.DNS_ROUNDED),
            (
                "statistics",
                t("nav.statistics", default="Statistics"),
                ft.Icons.BAR_CHART_ROUNDED,
            ),
            ("logs", t("nav.logs", default="Logs"), ft.Icons.TERMINAL_ROUNDED),
            (
                "settings",
                t("nav.settings", default="Settings"),
                ft.Icons.SETTINGS_ROUNDED,
            ),
        ]

        self._buttons_container = ft.Column(
            spacing=8,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self._build_nav_buttons()

        self._change_server_btn = ft.Container(
            content=ft.Icon(ft.Icons.SWAP_HORIZ_ROUNDED, size=18, color=ft.Colors.WHITE),
            padding=ft.Padding.all(10),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.12, "#a855f7"),
            border=ft.Border.all(1.2, ft.Colors.with_opacity(0.6, "#a855f7")),
            tooltip=t("dashboard.change_server", default="Change Server"),
            alignment=ft.Alignment.CENTER,
            on_click=self._handle_change_server_click,
            ink=True,
        )

        self._quick_action_icon = ft.Icon(ft.Icons.BOLT, size=18, color="#f43f5e")

        self._quick_action_btn = ft.Container(
            content=self._quick_action_icon,
            padding=ft.Padding.all(10),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.08, "#f43f5e"),
            border=ft.Border.all(1.0, ft.Colors.with_opacity(0.25, "#f43f5e")),
            tooltip=t("dashboard.quick_disconnect", default="Quick Disconnect"),
            alignment=ft.Alignment.CENTER,
            on_click=self._on_connect_click,
            ink=True,
        )

        self._actions_panel = ft.Column(
            [
                self._change_server_btn,
                self._quick_action_btn,
            ],
            spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        super().__init__(
            content=ft.Column(
                [
                    self._buttons_container,
                    self._actions_panel,
                ],
                spacing=16,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
            width=70,
            padding=ft.Padding.symmetric(vertical=16, horizontal=8),
            bgcolor=ft.Colors.with_opacity(0.4, "#0b0518"),
            border=ft.Border.only(right=ft.BorderSide(1, ft.Colors.with_opacity(0.12, "#a855f7"))),
        )

    def _handle_change_server_click(self, e):
        if self._on_change_server_click:
            self._on_change_server_click(e)

    def set_active_tab(self, tab_id: str):
        """Set the current active navigation tab."""
        if self._active_tab == tab_id:
            return
        self._active_tab = tab_id
        self._apply_active_styles()
        try:
            if self.page:
                self._buttons_container.update()
        except Exception:
            pass

    def update_connect_button_text(self, text: str, is_running: bool, server_name: str = ""):
        """Update quick action icon button tooltip and style matching connection status."""
        btn_tooltip = (
            t("dashboard.quick_disconnect", default="Quick Disconnect")
            if is_running
            else t("dashboard.quick_connect", default="Quick Connect")
        )
        self._quick_action_btn.tooltip = btn_tooltip
        if is_running:
            self._quick_action_icon.color = "#f43f5e"
            self._quick_action_btn.bgcolor = ft.Colors.with_opacity(0.08, "#f43f5e")
            self._quick_action_btn.border = ft.Border.all(1.0, ft.Colors.with_opacity(0.25, "#f43f5e"))
        else:
            self._quick_action_icon.color = "#c084fc"
            self._quick_action_btn.bgcolor = ft.Colors.with_opacity(0.1, "#a855f7")
            self._quick_action_btn.border = ft.Border.all(1.0, ft.Colors.with_opacity(0.3, "#a855f7"))

        try:
            if self._quick_action_btn.page:
                self._quick_action_btn.update()
        except Exception:
            pass

    def _build_nav_buttons(self):
        """Build compact icon-only nav buttons with hover tooltips."""
        self._buttons_container.controls.clear()
        self._button_refs: dict[str, tuple[ft.Container, ft.Icon]] = {}
        for tab_id, label, icon in self._nav_items:
            is_active = tab_id == self._active_tab
            icon_ctrl = ft.Icon(
                icon,
                size=20,
                color="#c084fc" if is_active else AppColors.ON_SURFACE_VARIANT,
            )
            btn = ft.Container(
                content=icon_ctrl,
                padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                border_radius=12,
                bgcolor=ft.Colors.with_opacity(0.2, "#6d28d9") if is_active else ft.Colors.TRANSPARENT,
                border=ft.Border.all(1.2, ft.Colors.with_opacity(0.5, "#a855f7")) if is_active else None,
                shadow=ft.BoxShadow(
                    spread_radius=0,
                    blur_radius=12,
                    color=ft.Colors.with_opacity(0.3, "#7c3aed"),
                    offset=ft.Offset(0, 0),
                )
                if is_active
                else None,
                tooltip=label,
                alignment=ft.Alignment.CENTER,
                on_click=lambda e, tid=tab_id: self._on_tab_change(tid),
            )
            self._button_refs[tab_id] = (btn, icon_ctrl)
            self._buttons_container.controls.append(btn)

    def _apply_active_styles(self):
        """Update existing button styles in-place without rebuilding controls."""
        for tab_id, (btn, icon_ctrl) in self._button_refs.items():
            is_active = tab_id == self._active_tab
            icon_ctrl.color = "#c084fc" if is_active else AppColors.ON_SURFACE_VARIANT
            btn.bgcolor = ft.Colors.with_opacity(0.2, "#6d28d9") if is_active else ft.Colors.TRANSPARENT
            btn.border = ft.Border.all(1.2, ft.Colors.with_opacity(0.5, "#a855f7")) if is_active else None
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
