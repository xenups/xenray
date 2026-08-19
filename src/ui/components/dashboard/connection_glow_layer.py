"""Outer animated glow layer for ConnectionButton."""

from __future__ import annotations

import flet as ft

from src.ui.helpers.button_theme_styles import (
    get_connected_shadow,
    get_connecting_shadow,
    get_disconnected_shadow,
    get_disconnecting_shadow,
)
from src.ui.helpers.glow_calculator import GlowMetrics


class ConnectionGlowLayer(ft.Container):
    """Container managing the outer ambient glow and network activity pulse."""

    def __init__(self):
        super().__init__(
            width=195,
            height=195,
            border_radius=97.5,
            bgcolor=ft.Colors.TRANSPARENT,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=24,
                color=ft.Colors.with_opacity(0.2, ft.Colors.BLACK),
                offset=ft.Offset(0, 0),
            ),
            opacity=1.0,
            animate_opacity=800,
            animate_scale=ft.Animation(800, ft.AnimationCurve.EASE_IN_OUT),
            animate=ft.Animation(600, ft.AnimationCurve.EASE_IN_OUT),
        )

    def set_connected_glow(self) -> None:
        """Apply the tight purple glow for connected state."""
        self.opacity = 1.0
        self.scale = 1.0
        self.shadow = get_connected_shadow()
        self.update_safe()

    def set_disconnected_glow(self) -> None:
        """Apply minimal dark shadow for disconnected state."""
        self.shadow = get_disconnected_shadow()
        self.update_safe()

    def set_connecting_glow(self) -> None:
        """Apply amber glow for connecting state."""
        self.opacity = 1.0
        self.scale = 1.0
        self.shadow = get_connecting_shadow()
        self.update_safe()

    def set_disconnecting_glow(self) -> None:
        """Apply red glow for disconnecting state."""
        self.opacity = 1.0
        self.scale = 1.0
        self.shadow = get_disconnecting_shadow()
        self.update_safe()

    def apply_activity_metrics(self, metrics: GlowMetrics) -> None:
        """Apply computed network activity glow metrics."""
        self.shadow = ft.BoxShadow(
            spread_radius=metrics.spread,
            blur_radius=metrics.blur,
            color=ft.Colors.with_opacity(metrics.opacity, "#8b5cf6"),
            offset=ft.Offset(0, 0),
        )
        self.scale = metrics.scale
        self.opacity = metrics.glow_opacity
        self.update_safe()

    def update_safe(self) -> None:
        """Safe update that silently ignores errors when not mounted."""
        try:
            self.update()
        except Exception:
            pass
