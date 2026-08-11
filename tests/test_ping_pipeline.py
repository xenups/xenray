"""Tests for the active-server ping pipeline (startup trigger + live EventBus binding)."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import flet as ft
import pytest

from src.core.event_bus import TOPIC_ACTIVE_SERVER_PING_UPDATED, event_bus
from src.ui.components.dashboard.connection_button import ConnectionButton
from src.ui.handlers.latency_monitor_handler import LatencyMonitorHandler
from src.ui.pages.dashboard_page import DashboardPage


def _wait_for(condition, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


class _FakeUiHelper:
    """Executes marshaled UI calls synchronously."""

    def call(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


def test_connection_button_renders_ping_result():
    button = ConnectionButton(on_click=lambda e: None)
    button.set_pre_connection_ping("123ms", True)
    assert button._status_text.value == "123ms"
    assert button._status_text.color == ft.Colors.GREEN_400

    button.set_pre_connection_ping("Timeout", False)
    assert button._status_text.color == ft.Colors.RED_400


def test_latency_monitor_publishes_ping_over_event_bus():
    handler = LatencyMonitorHandler(app_context=MagicMock())
    handler.setup(
        page=MagicMock(),
        status_display=MagicMock(),
        server_card=MagicMock(),
        server_list=MagicMock(),
        ui_helper=_FakeUiHelper(),
        is_running_getter=lambda: False,
        connecting_getter=lambda: False,
        selected_profile_getter=lambda: {"id": "p1", "config": {"x": 1}},
    )

    received = []

    def listener(data):
        received.append(data)

    event_bus.subscribe(TOPIC_ACTIVE_SERVER_PING_UPDATED, listener)
    try:
        with patch(
            "src.ui.handlers.latency_monitor_handler.ConnectionTester.test_connection_sync",
            return_value=(True, "123ms", None),
        ):
            handler.trigger_single_check()
            assert _wait_for(lambda: bool(received))
    finally:
        event_bus.unsubscribe(TOPIC_ACTIVE_SERVER_PING_UPDATED, listener)

    assert received == [{"ping_ms": 123, "success": True, "result_str": "123ms"}]


def test_in_flight_guard_prevents_request_stacking():
    handler = LatencyMonitorHandler(app_context=MagicMock())
    handler.setup(
        page=MagicMock(),
        status_display=MagicMock(),
        server_card=MagicMock(),
        server_list=MagicMock(),
        ui_helper=_FakeUiHelper(),
        is_running_getter=lambda: False,
        connecting_getter=lambda: False,
        selected_profile_getter=lambda: {"id": "p1", "config": {"x": 1}},
    )

    calls = []
    release = threading.Event()

    def fake_test(config, fetch_country=False):
        # Keep the ping in-flight (pending) so the PingManager dedup stays engaged.
        calls.append(1)
        release.wait(timeout=3.0)
        return (True, "123ms", None)

    with patch(
        "src.ui.handlers.latency_monitor_handler.ConnectionTester.test_connection_sync",
        side_effect=fake_test,
    ):
        handler.trigger_single_check()
        # Let the PingManager worker pick up the first (now in-flight) ping.
        time.sleep(0.2)
        # A second trigger for the same profile must be deduplicated.
        handler.trigger_single_check()
        time.sleep(0.2)

    release.set()
    time.sleep(0.2)
    assert len(calls) == 1


def test_dashboard_page_renders_ping_live_while_disconnected():
    button = ConnectionButton(on_click=lambda e: None)
    view = DashboardPage(
        on_toggle_click=lambda e: None,
        on_change_server_click=lambda e: None,
        connection_button=button,
    )
    try:
        assert button._status_text.value != "123ms"
        event_bus.publish(
            TOPIC_ACTIVE_SERVER_PING_UPDATED,
            {"ping_ms": 123, "success": True, "result_str": "123ms"},
        )
        assert button._status_text.value == "123ms"
        assert button._status_text.color == ft.Colors.GREEN_400
    finally:
        view.dispose()


def test_dashboard_page_ignores_ping_when_connected():
    button = ConnectionButton(on_click=lambda e: None)
    view = DashboardPage(
        on_toggle_click=lambda e: None,
        on_change_server_click=lambda e: None,
        connection_button=button,
    )
    try:
        view._is_connected = True
        event_bus.publish(
            TOPIC_ACTIVE_SERVER_PING_UPDATED,
            {"ping_ms": 123, "success": True, "result_str": "123ms"},
        )
        assert button._status_text.value != "123ms"
    finally:
        view.dispose()
