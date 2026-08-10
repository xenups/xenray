"""Unit tests for AppInitializer path resolution and window property configuration."""

from __future__ import annotations

import os

import flet as ft
import pytest

from src.core.app_initializer import AppInitializer


def test_app_initializer_icon_path_resolution():
    """Test get_absolute_icon_path returns existing icon file path."""
    icon_path = AppInitializer.get_absolute_icon_path()
    assert icon_path.endswith("icon.ico")
    assert os.path.exists(icon_path)


def test_app_initializer_configure_window_properties():
    """Test configure_window_properties configures page window geometry specs."""

    class MockWindow:
        def __init__(self):
            self.title = ""
            self.icon = ""
            self.width = 0
            self.height = 0
            self.min_width = 0
            self.min_height = 0
            self.max_width = 0
            self.max_height = 0
            self.resizable = True
            self.minimizable = False
            self.maximizable = True
            self.prevent_close = False
            self.title_bar_hidden = False
            self.title_bar_buttons_hidden = False

    class MockPage:
        def __init__(self):
            self.window = MockWindow()
            self.title = ""
            self.padding = -1
            self.spacing = -1
            self.bgcolor = ""

        def update(self):
            pass

    page = MockPage()
    AppInitializer.configure_window_properties(page)

    assert page.window.width == 620
    assert page.window.height == 480
    assert page.window.resizable == False
    assert page.window.prevent_close == True
    assert page.window.title_bar_hidden == True
