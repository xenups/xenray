"""Unit tests for XrayCoreCard component and Xray-Core update checking workflow."""

from __future__ import annotations

from unittest.mock import MagicMock

import flet as ft
import pytest

from src.ui.components.settings.xray_core_card import XrayCoreCard
from src.ui.controllers.settings_controller import SettingsController


@pytest.fixture
def mock_app_context():
    """Create a mock app context with in-memory settings."""

    class MockSettings:
        def __init__(self):
            self.proxy_port = 10808
            self.http_port = 10809
            self.tun_engine = "sing-box"
            self.routing_country = "ir"
            self.language = "en"
            self.auto_reconnect = True

        def get_proxy_port(self):
            return self.proxy_port

        def set_proxy_port(self, val: int):
            self.proxy_port = val

        def get_http_port(self):
            return self.http_port

        def set_http_port(self, val: int):
            self.http_port = val

        def get_tun_engine(self):
            return self.tun_engine

        def set_tun_engine(self, val: str):
            self.tun_engine = val

        def get_routing_country(self):
            return self.routing_country

        def set_routing_country(self, val: str):
            self.routing_country = val

        def get_language(self):
            return self.language

        def set_language(self, val: str):
            self.language = val

        def set_auto_reconnect_enabled(self, enabled: bool):
            self.auto_reconnect = enabled

    ctx = MagicMock()
    ctx.settings = MockSettings()
    return ctx


def test_xray_core_card_initialization_and_checking_state():
    """Test XrayCoreCard UI controls and loading state toggle."""
    clicks = []
    card = XrayCoreCard(on_check_core_click=lambda e: clicks.append(True))

    assert isinstance(card, ft.Container)
    assert card._title_text.value == "Xray-Core"

    card.set_checking(True)
    assert card._update_btn.disabled is True
    assert card._progress_ring.visible is True
    assert card._btn_icon.visible is False

    card.set_checking(False)
    assert card._update_btn.disabled is False
    assert card._progress_ring.visible is False
    assert card._btn_icon.visible is True


def test_check_xray_core_update_flow(mock_app_context, monkeypatch):
    """Test check_xray_core_update controller flow for up-to-date and update available states."""
    toasts = []
    ctrl = SettingsController(app_context=mock_app_context, toast_callback=lambda m, t: toasts.append((m, t)))

    card_mock = MagicMock()

    # 1. Test up-to-date response
    monkeypatch.setattr(
        "src.services.xray_installer.XrayInstallerService.check_for_updates",
        lambda: (False, "26.7.28", "26.7.28"),
    )
    avail, curr, latest = ctrl.check_xray_core_update(core_card_ref=card_mock, sync=True)
    assert avail is False
    assert toasts[-1][1] == "success"
    assert "به روز است" in toasts[-1][0] or "up to date" in toasts[-1][0].lower()
    card_mock.set_checking.assert_any_call(True)
    card_mock.set_checking.assert_any_call(False)

    # 2. Test update available response
    monkeypatch.setattr(
        "src.services.xray_installer.XrayInstallerService.check_for_updates",
        lambda: (True, "26.7.28", "26.8.0"),
    )
    avail, curr, latest = ctrl.check_xray_core_update(core_card_ref=card_mock, sync=True)
    assert avail is True
    assert latest == "26.8.0"
    assert toasts[-1][1] == "success"
