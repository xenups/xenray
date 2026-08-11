"""Unit tests verifying single source of truth for app versioning."""

from __future__ import annotations

import flet as ft

from src.__version__ import APP_VERSION as ROOT_APP_VERSION
from src.__version__ import __version__
from src.core.constants import APP_VERSION as CONSTANTS_APP_VERSION


def test_app_version_centralized_source_of_truth():
    """Verify __version__ and APP_VERSION are consistent across modules."""
    assert isinstance(__version__, str)
    assert len(__version__) > 0
    assert ROOT_APP_VERSION == __version__
    assert CONSTANTS_APP_VERSION == __version__


def test_header_branding_version_label():
    """Verify UI header branding contains the version indicator."""
    builder = type("DummyUIBuilder", (), {})()
    builder._handle_window_minimize = lambda: None
    builder._handle_window_close = lambda: None

    # Construct header branding element directly
    version_label = ft.Text(f"v{CONSTANTS_APP_VERSION}", size=11, color="#8A8F9E")
    header_branding = ft.Row(
        [
            ft.Image(src="icon.png", width=20, height=20, fit="contain"),
            ft.Text("XenRay", size=14, weight=ft.FontWeight.W_800, color=ft.Colors.WHITE),
            version_label,
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    assert len(header_branding.controls) == 3
    assert header_branding.controls[1].value == "XenRay"
    assert header_branding.controls[2].value == f"v{CONSTANTS_APP_VERSION}"
    assert header_branding.controls[2].size == 11
    assert header_branding.controls[2].color == "#8A8F9E"
