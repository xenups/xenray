"""Left Navigation Sidebar Component - Collapsed Compact Icon-Only Navigation Rail (70px)."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.controllers.navigation_controller import NavigationController
from src.ui.theme import AppColors


class NavSidebar(ft.Container):
    """Compact collapsed icon-only navigation sidebar rail matching 70px width spec."""

    def __init__(
        self,
        active_tab: str,
        on_tab_change: Callable[[str], None],
        on_connect_click: Callable,
        on_change_server_click: Callable | None = None,
        on_lan_click: Callable | None = None,
        allow_lan: bool = False,
    ):
        self._on_tab_change = on_tab_change
        self._on_connect_click = on_connect_click
        self._on_change_server_click = on_change_server_click
        self._on_lan_click = on_lan_click

        self._controller = NavigationController(
            initial_tab=active_tab,
            allow_lan=allow_lan,
            on_tab_changed=None,
        )

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

        # ── Apple-Style Sliding Active Indicator Overlay ─────────────────────
        self._active_indicator = ft.Container(
            width=44,
            height=44,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.15, AppColors.PRIMARY),
            border=ft.Border.all(1.5, AppColors.PRIMARY),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=12,
                color=ft.Colors.with_opacity(0.35, AppColors.PRIMARY),
                offset=ft.Offset(0, 0),
            ),
            animate_position=ft.Animation(350, curve=ft.AnimationCurve.DECELERATE),
            animate_opacity=ft.Animation(200),
            top=0,
            left=5,
        )

        self._buttons_container = ft.Column(
            spacing=8,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            left=5,
            width=44,
        )
        self._build_nav_buttons()

        self._nav_stack = ft.Stack(
            controls=[
                self._active_indicator,
                self._buttons_container,
            ],
            width=54,
            height=len(self._nav_items) * 44 + (len(self._nav_items) - 1) * 8,
        )

        # ── Quick Connect / Disconnect bolt ─────────────────────────────────
        qc_style = self._controller.get_quick_connect_style(is_running=False)
        self._quick_action_icon = ft.Icon(ft.Icons.BOLT, size=18, color=qc_style.icon_color)

        self._quick_action_btn = ft.Container(
            content=self._quick_action_icon,
            padding=ft.Padding.all(10),
            border_radius=12,
            bgcolor=qc_style.bgcolor,
            border=qc_style.border,
            tooltip=qc_style.tooltip,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_connect_click,
            ink=True,
        )

        # ── LAN Sharing button ──────────────────────────────────────────────
        lan_style = self._controller.get_lan_button_style()
        self._lan_icon = ft.Icon(
            ft.Icons.WIFI_TETHERING_ROUNDED,
            size=18,
            color=lan_style.icon_color,
        )
        # Status light dot: fades in/out (GPU-native 700ms EASE_OUT) like a
        # radio station lamp when LAN sharing is enabled/disabled.
        self._lan_indicator = ft.Container(
            width=6,
            height=6,
            border_radius=3,
            bgcolor="#4ADE80",
            opacity=1.0 if allow_lan else 0.15,
            animate_opacity=ft.Animation(700, curve=ft.AnimationCurve.EASE_OUT),
        )
        self._lan_btn = ft.Container(
            content=ft.Stack(
                [
                    self._lan_icon,
                    self._lan_indicator,
                ],
                width=24,
                height=24,
                # Dot sits at the button's top-right corner (status lamp)
                alignment=ft.Alignment(1, -1),
            ),
            padding=ft.Padding.all(10),
            border_radius=12,
            bgcolor=lan_style.bgcolor,
            border=lan_style.border,
            shadow=lan_style.shadow,
            tooltip=t("lan.page_title", default="LAN Sharing"),
            alignment=ft.Alignment.CENTER,
            on_click=self._handle_lan_click,
            ink=True,
        )

        self._actions_panel = ft.Column(
            [
                self._lan_btn,
                self._quick_action_btn,
            ],
            spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        super().__init__(
            content=ft.Column(
                [
                    self._nav_stack,
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

    @property
    def _active_tab(self) -> str:
        return self._controller.active_tab

    @_active_tab.setter
    def _active_tab(self, value: str) -> None:
        self._controller.set_active_tab(value)

    @property
    def _allow_lan(self) -> bool:
        return self._controller.allow_lan

    @_allow_lan.setter
    def _allow_lan(self, value: bool) -> None:
        self._controller.set_allow_lan(value)

    def _handle_lan_click(self, e):
        """Navigate to LAN page and mark it active in the sidebar."""
        self.set_active_tab("lan")
        if self._on_lan_click:
            self._on_lan_click(e)

    def update_lan_button(self, allow_lan: bool):
        """Update LAN button accent to reflect active/inactive LAN state."""
        self._controller.set_allow_lan(allow_lan)
        is_active = self._controller.active_tab == "lan"
        self._apply_lan_styles(is_active)

    def _update_indicator_position(self):
        """Calculate and set the indicator vertical Y-offset (top position) based on active tab."""
        tab_id = self._controller.active_tab
        nav_ids = [item[0] for item in self._nav_items]
        if tab_id in nav_ids:
            idx = nav_ids.index(tab_id)
            self._active_indicator.top = idx * 52
            self._active_indicator.opacity = 1
        else:
            self._active_indicator.opacity = 0

    def set_active_tab(self, tab_id: str):
        """Set the current active navigation tab with smooth indicator repositioning."""
        self._controller.set_active_tab(tab_id)
        self._update_indicator_position()
        self._apply_active_styles()
        self._apply_lan_styles(is_active=(tab_id == "lan"))
        try:
            if self.page:
                self._active_indicator.update()
                self._buttons_container.update()
        except Exception:
            pass

    def _apply_lan_styles(self, is_active: bool):
        style = self._controller.get_lan_button_style(tab_id="lan" if is_active else self._controller.active_tab)
        self._lan_icon.color = style.icon_color
        self._lan_btn.bgcolor = style.bgcolor
        self._lan_btn.border = style.border
        self._lan_btn.shadow = style.shadow
        # Status light: 1.0 (lit) when LAN sharing is on, 0.15 (dim) off.
        self._lan_indicator.opacity = 1.0 if self._controller.allow_lan else 0.15
        try:
            if self._lan_btn.page:
                self._lan_btn.update()
            if self._lan_indicator.page:
                self._lan_indicator.update()
        except Exception:
            pass

    def update_lan_badge(self, allow_lan: bool):
        """Alias for update_lan_button used by LanSharingPage toggle handler."""
        self.update_lan_button(allow_lan)

    def update_connect_button_text(self, text: str, is_running: bool, server_name: str = ""):
        """Update quick action icon button tooltip and style matching connection status."""
        style = self._controller.get_quick_connect_style(is_running)
        self._quick_action_btn.tooltip = style.tooltip
        self._quick_action_icon.color = style.icon_color
        self._quick_action_btn.bgcolor = style.bgcolor
        self._quick_action_btn.border = style.border

        try:
            if self._quick_action_btn.page:
                self._quick_action_btn.update()
        except Exception:
            pass

    def _handle_nav_click(self, tab_id: str, e=None):
        """Immediate hitbox click handler while indicator glides asynchronously."""
        self.set_active_tab(tab_id)
        self._on_tab_change(tab_id)

    def _build_nav_buttons(self):
        """Build compact icon-only nav buttons laid out over the active sliding indicator."""
        self._buttons_container.controls.clear()
        self._button_refs: dict[str, tuple[ft.Container, ft.Icon]] = {}
        for tab_id, label, icon in self._nav_items:
            style = self._controller.get_nav_item_style(tab_id)
            icon_ctrl = ft.Icon(
                icon,
                size=20,
                color=style.icon_color,
            )
            btn = ft.Container(
                content=icon_ctrl,
                width=44,
                height=44,
                border_radius=12,
                bgcolor=ft.Colors.TRANSPARENT,
                border=None,
                tooltip=label,
                alignment=ft.Alignment.CENTER,
                on_click=lambda e, tid=tab_id: self._handle_nav_click(tid, e),
                ink=True,
            )
            self._button_refs[tab_id] = (btn, icon_ctrl)
            self._buttons_container.controls.append(btn)
        self._update_indicator_position()

    def _apply_active_styles(self):
        """Update existing button icon styles in-place without rebuilding controls."""
        for tab_id, (btn, icon_ctrl) in self._button_refs.items():
            style = self._controller.get_nav_item_style(tab_id)
            icon_ctrl.color = style.icon_color
