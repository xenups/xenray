"""Theme Handler - Manages theme switching and persistence."""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING
import flet as ft

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class ThemeHandler:
    """Manages theme switching and persistence for the application."""

    def __init__(self, main_window: MainWindow):
        self._main = main_window

    def toggle_theme(self, e=None):
        """Toggles between dark and light themes."""
        page = self._main._page
        is_dark = page.theme_mode == ft.ThemeMode.DARK
        new_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        page.theme_mode = new_mode

        # Save preference in background to avoid blocking UI
        threading.Thread(
            target=self._main._config_manager.set_theme_mode,
            args=("light" if is_dark else "dark",),
            daemon=True,
        ).start()

        # Update specific components that have theme-dependent assets/colors
        if self._main._connection_button:
            self._main._connection_button.update_theme(not is_dark)
        if self._main._server_card:
            self._main._server_card.update_theme(not is_dark)
        if self._main._header:
            self._main._header.update_theme(not is_dark)

        # Force a page update to ensure theme mode change applies globally
        page.update()
