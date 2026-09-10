"""Unit tests for UI layer core update flows and permission handling."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, Mock, patch

from src.services.installer.archive_extractor import CorePermissionError
from src.ui.controllers.settings_controller import SettingsController
from src.ui.handlers.installer_handler import InstallerHandler


def test_installer_handler_xray_install():
    """InstallerHandler runs XrayInstallerService.install for component 'xray'."""
    conn_mgr = Mock()
    handler = InstallerHandler(connection_manager=conn_mgr)

    mock_page = Mock()
    mock_toast = Mock()
    mock_ui_helper = Mock()
    mock_ui_helper.call.side_effect = lambda f: f()

    handler.setup(page=mock_page, ui_helper=mock_ui_helper, toast=mock_toast)

    with patch("src.services.installer.xray_installer.XrayInstallerService.install") as mock_install:
        handler.run_specific_installer("xray")
        time.sleep(0.1)
        mock_install.assert_called_once()
        mock_toast.show.assert_called_once()


def test_installer_handler_singbox_install():
    """InstallerHandler runs SingboxInstallerService.install for component 'singbox'."""
    conn_mgr = Mock()
    handler = InstallerHandler(connection_manager=conn_mgr)

    mock_page = Mock()
    mock_toast = Mock()
    mock_ui_helper = Mock()
    mock_ui_helper.call.side_effect = lambda f: f()

    handler.setup(page=mock_page, ui_helper=mock_ui_helper, toast=mock_toast)

    with patch("src.services.installer.singbox_installer.SingboxInstallerService.install") as mock_install:
        handler.run_specific_installer("singbox")
        time.sleep(0.1)
        mock_install.assert_called_once()
        mock_toast.show.assert_called_once()


def test_installer_handler_permission_error_elevation():
    """InstallerHandler presents admin elevation dialog when CorePermissionError occurs."""
    conn_mgr = Mock()
    handler = InstallerHandler(connection_manager=conn_mgr)

    mock_page = Mock()
    mock_toast = Mock()
    mock_ui_helper = Mock()
    mock_ui_helper.call.side_effect = lambda f: f()

    handler.setup(page=mock_page, ui_helper=mock_ui_helper, toast=mock_toast)

    perm_err = CorePermissionError("Administrator privileges required")

    with patch(
        "src.services.installer.xray_installer.XrayInstallerService.install",
        side_effect=perm_err,
    ):
        with patch("src.utils.process_utils.ProcessUtils.is_admin", return_value=False):
            handler.run_specific_installer("xray")
            time.sleep(0.1)
            mock_toast.show.assert_called_with("Administrator privileges required", "error")
            mock_page.show_dialog.assert_called()


def test_settings_controller_permission_error_shows_admin_dialog():
    """SettingsController._show_xray_core_update_dialog catches PermissionError and shows admin dialog."""
    mock_app_context = MagicMock()
    mock_page = MagicMock()
    ctrl = SettingsController(app_context=mock_app_context)

    perm_err = CorePermissionError("Write access denied. Run as admin.")

    with patch("src.services.installer.xray_installer.XrayInstallerService.install", side_effect=perm_err):
        with patch("src.utils.process_utils.ProcessUtils.is_admin", return_value=False):

            def capture_dialog(dlg):
                # Trigger confirm click (Install & Update action button)
                install_btn = dlg.actions[1]
                install_btn.on_click(MagicMock())

            mock_page.show_dialog.side_effect = capture_dialog

            ctrl._show_xray_core_update_dialog(mock_page, "25.1.1", "26.7.28")
            time.sleep(0.1)

            # Assert dialog was shown again for admin restart
            assert mock_page.show_dialog.call_count >= 2
