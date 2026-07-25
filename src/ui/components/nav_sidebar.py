"""Left Navigation Sidebar Component with Clean Empty Top (Apple macOS style) & Quick-Action Card."""
from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors


class NavSidebar(ft.Container):
    """Sidebar navigation drawer matching macOS Apple Dark design specs."""

    def __init__(self, active_tab: str, on_tab_change: Callable[[str], None], on_connect_click: Callable):
        self._active_tab = active_tab
        self._on_tab_change = on_tab_change
        self._on_connect_click = on_connect_click

        self._nav_items = [
            ("dashboard", t("nav.dashboard", default="Dashboard"), ft.Icons.GRID_VIEW),
            ("servers", t("nav.servers", default="Servers"), ft.Icons.DNS),
            ("logs", t("nav.logs", default="Logs"), ft.Icons.TERMINAL),
            ("settings", t("nav.settings", default="Settings"), ft.Icons.SETTINGS),
        ]

        self._buttons_container = ft.Column(spacing=6, expand=True)
        self._build_nav_buttons()

        # Sleek Compact Quick-Action Card Widget
        self._quick_server_name = ft.Text(
            t("server_list.no_server", default="No Server Selected"),
            size=11,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.WHITE,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
        )

        self._quick_action_text = ft.Text(
            t("dashboard.quick_connect", default="Quick Connect"),
            size=11,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.WHITE,
        )
        self._quick_action_icon = ft.Icon(ft.Icons.BOLT, size=14, color=AppColors.PRIMARY)

        self._quick_action_btn = ft.OutlinedButton(
            content=ft.Row(
                [
                    self._quick_action_icon,
                    self._quick_action_text,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=4,
            ),
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                side=ft.BorderSide(1, ft.Colors.with_opacity(0.35, AppColors.PRIMARY)),
                padding=ft.Padding.symmetric(vertical=8, horizontal=10),
            ),
            width=float("inf"),
            on_click=self._on_connect_click,
        )

        self._quick_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.DNS, size=15, color=ft.Colors.WHITE),
                            self._quick_server_name,
                        ],
                        spacing=6,
                    ),
                    ft.Container(height=2),
                    self._quick_action_btn,
                ],
                spacing=4,
            ),
            padding=10,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.65, AppColors.SURFACE_CONTAINER),
            border=ft.Border.all(1, AppColors.GLASS_BORDER),
        )

        super().__init__(
            content=ft.Column(
                [
                    # Top empty area (macOS Apple sidebar style)
                    ft.Container(height=16),
                    # Navigation Options
                    self._buttons_container,
                    # Bottom Sleek Quick-Action Card Widget
                    self._quick_card,
                ],
                spacing=0,
                expand=True,
            ),
            width=210,
            padding=14,
            bgcolor=AppColors.SURFACE_CONTAINER_LOW,
            border=ft.Border.only(right=ft.BorderSide(1, AppColors.GLASS_BORDER)),
        )

    def set_active_tab(self, tab_id: str):
        """Set the current active navigation tab."""
        self._active_tab = tab_id
        self._build_nav_buttons()
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def update_connect_button_text(self, text: str, is_running: bool, server_name: str = ""):
        """Update the bottom quick action card state and active server display."""
        btn_text = (
            t("dashboard.quick_disconnect", default="Quick Disconnect")
            if is_running
            else t("dashboard.quick_connect", default="Quick Connect")
        )
        self._quick_action_text.value = btn_text
        icon_color = AppColors.ERROR if is_running else AppColors.PRIMARY
        self._quick_action_icon.color = icon_color
        self._quick_action_btn.style.side = ft.BorderSide(1, ft.Colors.with_opacity(0.4, icon_color))
        if server_name:
            self._quick_server_name.value = server_name
        try:
            self._quick_card.update()
        except Exception:
            pass

    def _build_nav_buttons(self):
        self._buttons_container.controls.clear()
        for tab_id, label, icon in self._nav_items:
            is_active = tab_id == self._active_tab
            btn = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            icon,
                            size=18,
                            color=AppColors.PRIMARY if is_active else AppColors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            label,
                            size=13,
                            weight=ft.FontWeight.W_700 if is_active else ft.FontWeight.W_500,
                            color=ft.Colors.WHITE if is_active else AppColors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=10,
                ),
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                border_radius=10,
                bgcolor=ft.Colors.with_opacity(0.15, AppColors.PRIMARY) if is_active else ft.Colors.TRANSPARENT,
                border=ft.Border.only(left=ft.BorderSide(3, AppColors.PRIMARY)) if is_active else None,
                on_click=lambda e, tid=tab_id: self._on_tab_change(tid),
            )
            self._buttons_container.controls.append(btn)
