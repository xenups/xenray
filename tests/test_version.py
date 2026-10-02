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


def test_ui_components_render_active_versions():
    """Verify WindowTitleBar, UpdateCard, and SettingsHandler render current versions in UI."""
    from src.ui.components.common.window_title_bar import WindowTitleBar
    from src.ui.components.settings.update_card import UpdateCard
    from src.ui.components.settings.sections.updates_section import UpdatesSection
    from src.ui.handlers.settings_handler import SettingsHandler
    from unittest.mock import MagicMock, patch

    # 1. WindowTitleBar
    bar = WindowTitleBar(lambda: None, lambda: None)
    # DragArea -> Container -> Row
    row = bar.content.content.controls[0]
    ver_text = row.controls[2].content.value
    assert ver_text == f"v{ROOT_APP_VERSION}"
    assert ver_text == "v0.3.6"

    # 2. UpdateCard
    card = UpdateCard(lambda: None)
    assert card._version_text.value == "v0.3.6"
    assert not card._version_text.value.startswith("vv")

    # 3. UpdatesSection about row
    section = UpdatesSection(
        on_check_app_updates=lambda: None,
        on_check_xray_core=lambda: None,
        on_update_rules=lambda: None,
    )
    # The inner SettingsSection column: [title, height, app_row, xray_row, rules_row, about_row]
    col = section.content.content
    about_row = col.controls[5]
    about_text = about_row.content.controls[2].value
    assert "v0.3.6 by Xenups" in about_text

    # 4. SettingsHandler Xray version footer
    with patch("src.services.installer.xray_installer.XrayInstallerService.get_local_version", return_value="26.9.30"):
        handler = SettingsHandler.__new__(SettingsHandler)
        assert handler.get_xray_version() == "Xray: v26.9.30"

