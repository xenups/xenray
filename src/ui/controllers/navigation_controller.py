"""Navigation Controller - manages sidebar navigation state, active tab evaluation, and dynamic style tokens."""

from __future__ import annotations

from typing import Callable, NamedTuple, Optional

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors


class LanButtonStyle(NamedTuple):
    """Style tokens for LAN Sharing button."""

    icon_color: str
    bgcolor: str
    border: Optional[ft.Border]
    shadow: Optional[ft.BoxShadow]


class QuickConnectStyle(NamedTuple):
    """Style tokens for Quick Connect button."""

    tooltip: str
    icon_color: str
    bgcolor: str
    border: ft.Border


class NavItemStyle(NamedTuple):
    """Style tokens for navigation rail item."""

    icon_color: str
    bgcolor: str
    border: Optional[ft.Border]
    shadow: Optional[ft.BoxShadow]


class NavigationController:
    """Controller handling navigation route selection and dynamic sidebar styling state."""

    def __init__(
        self,
        initial_tab: str = "dashboard",
        allow_lan: bool = False,
        sni_spoof_enabled: bool = False,
        on_tab_changed: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._active_tab: str = initial_tab
        self._allow_lan: bool = allow_lan
        self._sni_spoof_enabled: bool = sni_spoof_enabled
        self._on_tab_changed = on_tab_changed

    @property
    def active_tab(self) -> str:
        """Current active navigation tab ID."""
        return self._active_tab

    @property
    def allow_lan(self) -> bool:
        """Current LAN sharing enabled state."""
        return self._allow_lan

    @property
    def sni_spoof_enabled(self) -> bool:
        """Current SNI spoof enabled state."""
        return self._sni_spoof_enabled

    def set_active_tab(self, tab_id: str) -> None:
        """Update current active navigation tab."""
        self._active_tab = tab_id
        if self._on_tab_changed:
            self._on_tab_changed(tab_id)

    def set_allow_lan(self, allow_lan: bool) -> None:
        """Update LAN sharing enabled state."""
        self._allow_lan = allow_lan

    def set_sni_spoof_enabled(self, enabled: bool) -> None:
        """Update SNI spoof enabled state."""
        self._sni_spoof_enabled = bool(enabled)

    def get_lan_button_style(self, tab_id: Optional[str] = None) -> LanButtonStyle:
        """Compute dynamic LAN/TUN button style token based on active route and LAN switch state."""
        active_tab = tab_id if tab_id is not None else self._active_tab
        is_active = active_tab == "lan"

        if self._allow_lan:
            icon_color = "#4ADE80"
            bgcolor = ft.Colors.with_opacity(0.08, "#10B981")
            border = ft.Border.all(1.0, ft.Colors.with_opacity(0.25, "#10B981"))
            shadow = ft.BoxShadow(
                spread_radius=0,
                blur_radius=8,
                color=ft.Colors.with_opacity(0.20, "#10B981"),
                offset=ft.Offset(0, 0),
            )
        elif is_active:
            icon_color = "#FFFFFF"
            bgcolor = ft.Colors.with_opacity(0.18, "#A855F7")
            border = ft.Border.all(1.0, ft.Colors.with_opacity(0.35, "#A855F7"))
            shadow = ft.BoxShadow(
                spread_radius=0,
                blur_radius=10,
                color=ft.Colors.with_opacity(0.25, "#A855F7"),
                offset=ft.Offset(0, 0),
            )
        else:
            icon_color = "rgba(255, 255, 255, 0.45)"
            bgcolor = ft.Colors.with_opacity(0.03, ft.Colors.WHITE)
            border = ft.Border.all(1.0, ft.Colors.with_opacity(0.06, ft.Colors.WHITE))
            shadow = None

        return LanButtonStyle(
            icon_color=icon_color,
            bgcolor=bgcolor,
            border=border,
            shadow=shadow,
        )

    def get_quick_connect_style(self, is_running: bool) -> QuickConnectStyle:
        """Compute dynamic Quick Connect/Disconnect button style token based on connection status."""
        tooltip = (
            t("dashboard.quick_disconnect", default="Quick Disconnect")
            if is_running
            else t("dashboard.quick_connect", default="Quick Connect")
        )
        if is_running:
            return QuickConnectStyle(
                tooltip=tooltip,
                icon_color="#F87171",
                bgcolor=ft.Colors.with_opacity(0.08, "#EF4444"),
                border=ft.Border.all(1.0, ft.Colors.with_opacity(0.25, "#EF4444")),
            )
        return QuickConnectStyle(
            tooltip=tooltip,
            icon_color="rgba(255, 255, 255, 0.45)",
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
            border=ft.Border.all(1.0, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
        )

    def get_nav_item_style(self, item_tab_id: str) -> NavItemStyle:
        """Compute dynamic Nav Item style token based on active route."""
        is_active = item_tab_id == self._active_tab
        icon_color = "#FFFFFF" if is_active else "rgba(255, 255, 255, 0.45)"
        bgcolor = ft.Colors.with_opacity(0.18, "#A855F7") if is_active else ft.Colors.TRANSPARENT
        border = ft.Border.all(1.0, ft.Colors.with_opacity(0.35, "#A855F7")) if is_active else None
        shadow = (
            ft.BoxShadow(
                spread_radius=0,
                blur_radius=10,
                color=ft.Colors.with_opacity(0.25, "#A855F7"),
                offset=ft.Offset(0, 0),
            )
            if is_active
            else None
        )
        return NavItemStyle(
            icon_color=icon_color,
            bgcolor=bgcolor,
            border=border,
            shadow=shadow,
        )
