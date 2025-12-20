"""Theme Handler - Manages theme switching and persistence."""

from __future__ import annotations

import threading
from typing import Optional

import flet as ft

from src.core.config_manager import ConfigManager


class ThemeHandler:
    """Manages theme switching and persistence for the application."""

    def __init__(self, config_manager: ConfigManager):
        self._config_manager = config_manager
        self._page: Optional[ft.Page] = None
        self._connection_button = None
        self._server_card = None
        self._header = None

    def setup(
        self, page: ft.Page, connection_button=None, server_card=None, header=None
    ):
        """Bind UI components to the handler."""
        self._page = page
        self._connection_button = connection_button
        self._server_card = server_card
        self._header = header

    def toggle_theme(self, e=None):
        """Toggles between dark and light themes."""
        if not self._page:
            return

        is_dark = self._page.theme_mode == ft.ThemeMode.DARK
        new_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        self._page.theme_mode = new_mode

        # Save preference in background to avoid blocking UI
        threading.Thread(
            target=self._config_manager.set_theme_mode,
            args=("light" if is_dark else "dark",),
            daemon=True,
        ).start()

        # Update specific components that have theme-dependent assets/colors
        if self._connection_button:
            self._connection_button.update_theme(not is_dark)
        if self._server_card:
            self._server_card.update_theme(not is_dark)
        if self._header:
            self._header.update_theme(not is_dark)

        # Force a page update to ensure theme mode change applies globally
        self._page.update()
