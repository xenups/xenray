"""Unit tests for SettingsController validation, persistence, and EventBus emissions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.event_bus import event_bus
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

    ctx = MagicMock()
    ctx.settings = MockSettings()
    return ctx


def test_update_socks_port_valid_range(mock_app_context):
    """Test valid SOCKS port update persists and emits settings_updated over EventBus."""
    toasts = []
    events = []

    def toast_cb(msg, typ):
        toasts.append((msg, typ))

    def event_cb(data):
        events.append(data)

    event_bus.subscribe("settings_updated", event_cb)
    try:
        ctrl = SettingsController(app_context=mock_app_context, toast_callback=toast_cb)
        success, res = ctrl.update_socks_port(10810)

        assert success is True
        assert res == "10810"
        assert mock_app_context.settings.get_proxy_port() == 10810
        assert len(toasts) == 1
        assert toasts[0][1] == "success"
        assert len(events) == 1
        assert events[0] == {"setting": "socks_port", "value": 10810}
    finally:
        event_bus.unsubscribe("settings_updated", event_cb)


def test_update_socks_port_invalid_range(mock_app_context):
    """Test SOCKS port below 1024 or above 65535 is rejected."""
    toasts = []

    def toast_cb(msg, typ):
        toasts.append((msg, typ))

    ctrl = SettingsController(app_context=mock_app_context, toast_callback=toast_cb)

    # 1. Below range (80)
    success, err = ctrl.update_socks_port(80)
    assert success is False
    assert mock_app_context.settings.get_proxy_port() == 10808
    assert toasts[-1][1] == "error"

    # 2. Above range (70000)
    success, err = ctrl.update_socks_port(70000)
    assert success is False
    assert mock_app_context.settings.get_proxy_port() == 10808
    assert toasts[-1][1] == "error"


def test_update_socks_port_non_numeric(mock_app_context):
    """Test non-numeric SOCKS port input returns error."""
    toasts = []
    ctrl = SettingsController(app_context=mock_app_context, toast_callback=lambda m, t: toasts.append((m, t)))

    success, err = ctrl.update_socks_port("not_a_number")
    assert success is False
    assert mock_app_context.settings.get_proxy_port() == 10808
    assert toasts[-1][1] == "error"


def test_update_http_port_valid_and_invalid(mock_app_context):
    """Test HTTP port update validation, persistence, and EventBus emission."""
    toasts = []
    events = []

    def toast_cb(msg, typ):
        toasts.append((msg, typ))

    def event_cb(data):
        events.append(data)

    event_bus.subscribe("settings_updated", event_cb)
    try:
        ctrl = SettingsController(app_context=mock_app_context, toast_callback=toast_cb)

        # Valid HTTP port
        success, res = ctrl.update_http_port(10811)
        assert success is True
        assert res == "10811"
        assert mock_app_context.settings.get_http_port() == 10811
        assert events[-1] == {"setting": "http_port", "value": 10811}

        # Invalid HTTP port
        success, err = ctrl.update_http_port(50)
        assert success is False
        assert mock_app_context.settings.get_http_port() == 10811
        assert toasts[-1][1] == "error"
    finally:
        event_bus.unsubscribe("settings_updated", event_cb)


def test_update_tun_engine_and_country(mock_app_context):
    """Test TUN engine and routing country update handlers."""
    events = []
    event_bus.subscribe("settings_updated", lambda data: events.append(data))

    ctrl = SettingsController(app_context=mock_app_context)

    assert ctrl.update_tun_engine("xray") is True
    assert mock_app_context.settings.get_tun_engine() == "xray"

    assert ctrl.update_routing_country("de") is True
    assert mock_app_context.settings.get_routing_country() == "de"
