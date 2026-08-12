"""Window State Manager - Handles MainWindow state variables, page setup, and profile restoration."""

from __future__ import annotations

import os

import flet as ft

from src.core.app_context import AppContext
from src.core.constants import APPDIR
from src.core.types import ConnectionMode


class WindowStateManager:
    """Manages MainWindow setup parameters and profile state initialization."""

    @staticmethod
    def setup_page(page: ft.Page, app_context: AppContext) -> ConnectionMode:
        """Configure page parameters, window icon, and theme mode."""
        page.padding = 0
        page.theme_mode = ft.ThemeMode.DARK
        page.theme = ft.Theme()

        page.window.title_bar_hidden = True
        page.window.title_bar_buttons_hidden = True

        icon_path = os.path.join(APPDIR, "assets", "icon.ico")
        if os.path.exists(icon_path):
            page.window.icon = icon_path

        saved_mode = app_context.settings.get_connection_mode()
        saved_theme = app_context.settings.get_theme_mode()

        page.theme_mode = ft.ThemeMode.DARK if saved_theme == "dark" else ft.ThemeMode.LIGHT
        return ConnectionMode.VPN if saved_mode == "vpn" else ConnectionMode.PROXY

    @staticmethod
    def get_initial_selected_profile(app_context: AppContext) -> dict | None:
        """Load and return last selected profile from settings or subscriptions."""
        last_profile_id = app_context.settings.get_last_selected_profile_id()
        if last_profile_id:
            return app_context.get_profile_by_id(last_profile_id)
        return None
