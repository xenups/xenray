"""Tests for auto-inspection of newly imported servers (ping + location)."""

from __future__ import annotations

import time
from threading import Event
from unittest.mock import MagicMock, patch

import pytest

from src.core.event_bus import TOPIC_SERVER_INSPECTED, event_bus
from src.core.subscription_manager import SubscriptionManager
from src.services.server_inspector import ServerInspector, server_inspector
from src.ui.services.navigation_service import NavigationService


def _wait_for(condition, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_inspect_measures_ping_and_publishes_event():
    received = []
    event_bus.subscribe(TOPIC_SERVER_INSPECTED, lambda d: received.append(d))
    try:
        with patch(
            "src.services.server_inspector.ConnectionTester.test_connection_sync",
            return_value=(
                True,
                "Latency: 142ms",
                {"country_code": "US", "country_name": "United States", "city": "LA"},
            ),
        ):
            inspector = ServerInspector()
            inspector.inspect(
                {
                    "id": "abc",
                    "name": "Test",
                    "config": {"outbounds": [{"protocol": "vless"}]},
                }
            )
            # Wait INSIDE the patch scope: the PingManager worker must still see
            # the mocked test_connection_sync when it runs.
            assert _wait_for(lambda: bool(received))

        event = received[-1]
        assert event["server_id"] == "abc"
        assert event["ping"] == 142
        assert event["success"] is True
        assert event["location"]["country_code"] == "US"
        assert event["location"]["country_name"] == "United States"
    finally:
        event_bus.unsubscribe(TOPIC_SERVER_INSPECTED, lambda d: received.append(d))


def test_inspect_batch_processes_all_profiles_concurrently():
    received = []
    event_bus.subscribe(TOPIC_SERVER_INSPECTED, lambda d: received.append(d))
    try:
        profiles = [
            {
                "id": f"p{i}",
                "name": f"S{i}",
                "config": {"outbounds": [{"protocol": "vless"}]},
            }
            for i in range(5)
        ]
        with patch(
            "src.services.server_inspector.ConnectionTester.test_connection_sync",
            return_value=(
                True,
                "100ms",
                {"country_code": "DE", "country_name": "Germany"},
            ),
        ):
            inspector = ServerInspector()
            inspector.inspect_batch(profiles)
            # Wait INSIDE the patch scope so the worker sees the mocked call.
            assert _wait_for(lambda: len(received) >= 5)

        assert {e["server_id"] for e in received} == {f"p{i}" for i in range(5)}
    finally:
        event_bus.unsubscribe(TOPIC_SERVER_INSPECTED, lambda d: received.append(d))


def test_add_server_profile_triggers_inspection():
    mw = MagicMock()
    mw._app_context.profiles.save.return_value = "pid-1"
    mw._server_list = MagicMock()

    inspected = []

    def fake_inspect(profile):
        inspected.append(profile)

    with patch(
        "src.services.server_inspector.server_inspector.inspect",
        side_effect=fake_inspect,
    ) as mock_inspect:
        NavigationService(mw).add_server_profile("My Server", {"outbounds": []})

    mock_inspect.assert_called_once()
    assert inspected[0]["id"] == "pid-1"
    assert inspected[0]["name"] == "My Server"
    assert inspected[0]["config"] == {"outbounds": []}


def test_update_subscription_inspects_batch_after_parse():
    ctx = MagicMock()
    ctx.subscriptions.load_all.return_value = [{"id": "sub-1", "name": "Sub", "url": "http://x", "profiles": []}]
    ctx.subscriptions.update = MagicMock()

    done = Event()
    batch_calls = []

    def fake_fetch(url):
        return [
            {
                "id": f"p{i}",
                "name": f"S{i}",
                "config": {"outbounds": [{"protocol": "vless"}]},
            }
            for i in range(3)
        ]

    def fake_inspect_batch(profiles):
        batch_calls.append(profiles)
        done.set()

    manager = SubscriptionManager(ctx)
    with (
        patch.object(manager, "fetch_subscription", side_effect=fake_fetch),
        patch(
            "src.services.server_inspector.server_inspector.inspect_batch",
            side_effect=fake_inspect_batch,
        ),
    ):
        manager.update_subscription("sub-1")
        assert done.wait(timeout=3.0)

    assert len(batch_calls) == 1
    assert len(batch_calls[0]) == 3
    ctx.subscriptions.update.assert_called_once()
