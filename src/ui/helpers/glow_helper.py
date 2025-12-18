"""Glow Helper - Manages Earth horizon glow animations."""
from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class GlowHelper:
    """Manages Earth horizon glow effects."""

    def __init__(self, main_window: MainWindow):
        self._main = main_window

    def update_horizon_glow(self, state: str):
        """
        Update horizon glow color based on state.
        
        Args:
            state: 'connecting', 'connected', or 'disconnected'
        """
        if not self._main._earth_glow:
            return

        if state == "connecting":
            # Amber rim light
            self._main._earth_glow.gradient.colors = [
                ft.Colors.with_opacity(0.8, ft.Colors.AMBER),
                ft.Colors.with_opacity(0.3, ft.Colors.AMBER_700),
                ft.Colors.with_opacity(0.0, ft.Colors.TRANSPARENT),
            ]
            self._main._earth_glow.opacity = 1.0

        elif state == "connected":
            # Purple rim light
            self._main._earth_glow.gradient.colors = [
                ft.Colors.with_opacity(0.6, ft.Colors.PURPLE),
                ft.Colors.with_opacity(0.2, ft.Colors.PURPLE_700),
                ft.Colors.with_opacity(0.0, ft.Colors.TRANSPARENT),
            ]
            self._main._earth_glow.opacity = 0.8

        elif state == "disconnecting":
            # Red rim light
            self._main._earth_glow.gradient.colors = [
                ft.Colors.with_opacity(0.8, ft.Colors.RED),
                ft.Colors.with_opacity(0.3, ft.Colors.RED_700),
                ft.Colors.with_opacity(0.0, ft.Colors.TRANSPARENT),
            ]
            self._main._earth_glow.opacity = 1.0

        else:  # disconnected
            self._main._earth_glow.opacity = 0.0

        if self._main._earth_glow.page:
            self._main._earth_glow.update()
