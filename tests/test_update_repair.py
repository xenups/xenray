"""Unit tests verifying repair of Client & Xray-Core Update Buttons, i18n keys,
pre-releases, and version constant bindings."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from src.__version__ import APP_VERSION
from src.core.i18n import I18n, set_language
from src.services.installer.xray_installer import XrayInstallerService
from src.ui.components.common.toast import ToastManager
from src.ui.components.settings.update_card import UpdateCard
from src.ui.components.settings.xray_core_card import XrayCoreCard
from src.ui.controllers.settings_controller import SettingsController
from src.ui.pages.settings_page import SettingsPage


@pytest.fixture(autouse=True)
def reset_i18n():
    """Reset I18n singleton before each test."""
    import src.core.i18n

    I18n._instance = None
    I18n._translations = {}
    I18n._current_lang = "en"
    src.core.i18n._i18n = I18n()
    yield


def test_i18n_translation_keys_exist_in_all_locales():
    """Verify that all critical update translation keys exist across en, fa, ru, zh locale files."""
    locales_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets",
        "locales",
    )
    required_keys = [
        "check_core_update",
        "checking_core_updates",
        "xray_core_version",
        "checking_updates",
        "check_updates",
        "xray_core_update_title",
        "xray_core_update_message",
        "xray_core_update_available",
        "xray_core_up_to_date",
        "xray_core_check_failed",
        "updating_xray_core",
        "xray_core_updated",
        "xray_core_update_failed",
        "update_available",
        "up_to_date",
        "update_check_failed",
        "version",
    ]

    for lang in ["en", "fa", "ru", "zh"]:
        file_path = os.path.join(locales_dir, f"{lang}.json")
        assert os.path.exists(file_path), f"Locale file missing for {lang}"
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        settings_dict = data.get("settings", {})
        for k in required_keys:
            assert k in settings_dict, f"Key '{k}' missing in settings of {lang}.json"


def test_xray_core_card_i18n_english_fallback_and_label_updates():
    """Verify XrayCoreCard renders English text when language is set to English and updates labels."""
    set_language("en")
    card = XrayCoreCard(on_check_core_click=lambda e: None)

    assert card._btn_text.value == "Check Core Update"

    set_language("fa")
    card.update_labels()
    assert "آپدیت هسته" in card._btn_text.value or "بررسی" in card._btn_text.value

    set_language("en")
    card.update_labels()
    assert card._btn_text.value == "Check Core Update"


def test_update_card_consumes_central_version_constant():
    """Verify UpdateCard uses APP_VERSION from src.__version__ instead of static hardcoded v1.0.0."""
    set_language("en")
    card = UpdateCard(on_check_update_click=lambda e: None)

    expected_display = f"v{APP_VERSION}" if not str(APP_VERSION).startswith("v") else APP_VERSION
    assert expected_display in card._version_text.value
    assert "v1.0.0 by Xenups" not in card._version_text.value


def test_xray_installer_service_pre_release_support():
    """Verify XrayInstallerService fetches and parses pre-release tags properly."""
    mock_releases = [
        {"tag_name": "v26.7.28-pre1", "prerelease": True},
        {"tag_name": "v25.1.1", "prerelease": False},
    ]

    class MockResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return mock_releases

    with patch("requests.get", return_value=MockResponse()):
        with patch.object(XrayInstallerService, "get_local_version", return_value="25.1.1"):
            # include_prerelease=True should select v26.7.28-pre1
            avail, curr, latest = XrayInstallerService.check_for_updates(include_prerelease=True)
            assert avail is True
            assert curr == "25.1.1"
            assert latest == "26.7.28-pre1"

            # include_prerelease=False should select v25.1.1
            avail_stable, curr_stable, latest_stable = XrayInstallerService.check_for_updates(include_prerelease=False)
            assert avail_stable is False
            assert latest_stable == "25.1.1"


def test_settings_page_click_handlers_and_toast_error_handling():
    """Verify SettingsPage delegates clicks to SettingsController and handles errors with error toast."""
    mock_ctrl = MagicMock()
    mock_ctrl.check_for_updates.side_effect = RuntimeError("Network down")

    mode_switch = MagicMock()
    mode_switch.value = True
    tun_engine = MagicMock()
    port_row = MagicMock()
    country_row = MagicMock()
    language_row = MagicMock()
    reconnect_row = MagicMock()
    startup_row = MagicMock()

    page = SettingsPage(
        mode_switch_row=mode_switch,
        tun_engine_row=tun_engine,
        port_row=port_row,
        country_row=country_row,
        language_row=language_row,
        reconnect_row=reconnect_row,
        startup_row=startup_row,
        settings_controller=mock_ctrl,
    )

    mock_event = MagicMock()
    mock_event.page = MagicMock()

    with patch.object(ToastManager, "show_error") as mock_toast_error:
        page._update_card._handle_click(mock_event)
        mock_ctrl.check_for_updates.assert_called_once()
        mock_toast_error.assert_called_once()
        assert "Network down" in mock_toast_error.call_args[0][1]


def test_settings_controller_installs_target_version():
    """Verify check_xray_core_update passes target_version=latest to XrayInstallerService.install."""
    mock_app_context = MagicMock()
    mock_page = MagicMock()
    ctrl = SettingsController(app_context=mock_app_context)

    with patch("src.services.installer.xray_installer.XrayInstallerService.install") as mock_install:
        mock_install.return_value = True

        def capture_dialog(dlg):
            # Simulate clicking the Install & Update action button (2nd action)
            install_btn = dlg.actions[1]
            install_btn.on_click(MagicMock())

        mock_page.show_dialog.side_effect = capture_dialog

        ctrl._show_xray_core_update_dialog(mock_page, "25.1.1", "26.7.28")
        import time

        time.sleep(0.1)

        mock_install.assert_called_with(target_version="26.7.28")


def test_update_button_frozen_dimensions():
    """Verify UpdateCard/XrayCoreCard buttons retain compact dimensions
    (explicit width=170 inside the 180 wrapper, height=32) across checking
    state toggles — the label swap must NEVER resize the button."""
    card = UpdateCard(on_check_update_click=lambda e: None)
    assert card._update_btn.width == 170  # explicit width: label swap can't resize
    assert card._update_btn.height == 32

    card.set_checking(True)
    assert card._update_btn.width == 170
    assert card._update_btn.height == 32

    card.set_checking(False)
    assert card._update_btn.width == 170
    assert card._update_btn.height == 32

    core_card = XrayCoreCard(on_check_core_click=lambda e: None)
    assert core_card._update_btn.width == 170
    assert core_card._update_btn.height == 32

    core_card.set_checking(True)
    assert core_card._update_btn.width == 170
    assert core_card._update_btn.height == 32

    core_card.set_checking(False)
    assert core_card._update_btn.width == 170
    assert core_card._update_btn.height == 32


def test_toast_manager_no_full_page_update():
    """Verify ToastManager uses targeted overlay updates without triggering 0-arg page.update()."""
    mock_page = MagicMock()
    mock_page.overlay = []

    tm = ToastManager(mock_page)
    tm.show("Test message", "info")

    mock_page.update.assert_called_once()
    arg_passed = mock_page.update.call_args[0][0]
    assert arg_passed is mock_page.overlay
