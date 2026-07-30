"""Unit tests for WindowStateManager."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import flet as ft

from src.core.types import ConnectionMode
from src.ui.helpers.window_state_manager import WindowStateManager


class TestWindowStateManager(unittest.TestCase):
    """Test suite for WindowStateManager page setup and profile loading."""

    def setUp(self):
        self.mock_page = MagicMock(spec=ft.Page)
        self.mock_page.window = MagicMock()
        self.mock_context = MagicMock()

    def test_setup_page_vpn(self):
        self.mock_context.settings.get_connection_mode.return_value = "vpn"
        self.mock_context.settings.get_theme_mode.return_value = "dark"

        mode = WindowStateManager.setup_page(self.mock_page, self.mock_context)
        self.assertEqual(mode, ConnectionMode.VPN)
        self.assertEqual(self.mock_page.theme_mode, ft.ThemeMode.DARK)

    def test_setup_page_proxy(self):
        self.mock_context.settings.get_connection_mode.return_value = "proxy"
        self.mock_context.settings.get_theme_mode.return_value = "light"

        mode = WindowStateManager.setup_page(self.mock_page, self.mock_context)
        self.assertEqual(mode, ConnectionMode.PROXY)
        self.assertEqual(self.mock_page.theme_mode, ft.ThemeMode.LIGHT)

    def test_get_initial_selected_profile(self):
        self.mock_context.settings.get_last_selected_profile_id.return_value = "p123"
        self.mock_context.get_profile_by_id.return_value = {"id": "p123", "name": "Node"}

        prof = WindowStateManager.get_initial_selected_profile(self.mock_context)
        self.assertEqual(prof["id"], "p123")


if __name__ == "__main__":
    unittest.main()
