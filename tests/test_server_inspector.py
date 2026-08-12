"""Tests for auto-inspection of newly imported servers (ping + location)."""

from __future__ import annotations

import asyncio
import time
from threading import Event
from unittest.mock import MagicMock, patch

from src.core.event_bus import (
    TOPIC_SERVER_INSPECTED,
    TOPIC_SERVER_INSPECTING,
    event_bus,
)
from src.core.subscription_manager import SubscriptionManager
from src.services.server_inspector import ServerInspector
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


def test_inspect_publishes_inspecting_event_immediately():
    """Verify the inspecting event fires synchronously at submission (no queue wait)."""
    received = []
    event_bus.subscribe(TOPIC_SERVER_INSPECTING, lambda d: received.append(d))
    try:
        with patch("src.services.server_inspector.ping_manager.submit"):
            inspector = ServerInspector()
            inspector.inspect(
                {
                    "id": "abc",
                    "name": "Test",
                    "config": {"outbounds": [{"protocol": "vless"}]},
                }
            )
        # Published on submission, before the ping worker runs.
        assert any(e.get("server_id") == "abc" for e in received)
    finally:
        event_bus.unsubscribe(TOPIC_SERVER_INSPECTING, lambda d: received.append(d))


def test_inspect_batch_publishes_no_inspecting_events_at_submission():
    """Batch submission must NOT start every card's sweep at once — inspecting
    events fire only when each task acquires the Semaphore inside the worker."""
    received = []
    event_bus.subscribe(TOPIC_SERVER_INSPECTING, lambda d: received.append(d))
    try:
        profiles = [{"id": f"p{i}", "name": f"S{i}", "config": {"outbounds": []}} for i in range(3)]
        with patch("src.services.server_inspector.ping_manager.submit"):
            inspector = ServerInspector()
            inspector.inspect_batch(profiles)
        # Nothing published at submission — queued cards stay idle.
        assert received == []
    finally:
        event_bus.unsubscribe(TOPIC_SERVER_INSPECTING, lambda d: received.append(d))


def test_inspect_batch_emits_inspecting_inside_worker_scope():
    """Running the batch worker publishes inspecting -> inspected per active task
    (i.e. the 3 cards currently holding the Semaphore, not the whole list)."""
    received_start = []
    received_done = []
    event_bus.subscribe(TOPIC_SERVER_INSPECTING, lambda d: received_start.append(d))
    event_bus.subscribe(TOPIC_SERVER_INSPECTED, lambda d: received_done.append(d))
    try:
        profiles = [
            {
                "id": f"p{i}",
                "name": f"S{i}",
                "config": {"outbounds": [{"protocol": "vless"}]},
            }
            for i in range(4)
        ]
        with patch(
            "src.services.server_inspector.ConnectionTester.test_connection_sync",
            return_value=(
                True,
                "100ms",
                {"country_code": "US", "country_name": "United States"},
            ),
        ):
            inspector = ServerInspector()
            asyncio.run(inspector._inspect_batch_async(profiles))

        # Each active task emits inspecting then inspected.
        assert {e.get("server_id") for e in received_start} == {f"p{i}" for i in range(4)}
        assert {e.get("server_id") for e in received_done} == {f"p{i}" for i in range(4)}
    finally:
        event_bus.unsubscribe(TOPIC_SERVER_INSPECTING, lambda d: received_start.append(d))
        event_bus.unsubscribe(TOPIC_SERVER_INSPECTED, lambda d: received_done.append(d))


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


def test_update_subscription_skips_inspection_for_large_batch():
    """Batches larger than AUTO_INSPECT_LIMIT must NOT auto-inspect."""
    from src.services.server_inspector import AUTO_INSPECT_LIMIT

    ctx = MagicMock()
    ctx.subscriptions.load_all.return_value = [{"id": "sub-1", "name": "Sub", "url": "http://x", "profiles": []}]
    ctx.subscriptions.update = MagicMock()

    batch_calls = []

    def fake_fetch(url):
        # One MORE than the auto-inspect threshold
        return [
            {
                "id": f"p{i}",
                "name": f"S{i}",
                "config": {"outbounds": [{"protocol": "vless"}]},
            }
            for i in range(AUTO_INSPECT_LIMIT + 1)
        ]

    def fake_inspect_batch(profiles):
        batch_calls.append(profiles)

    manager = SubscriptionManager(ctx)
    with (
        patch.object(manager, "fetch_subscription", side_effect=fake_fetch),
        patch(
            "src.services.server_inspector.server_inspector.inspect_batch",
            side_effect=fake_inspect_batch,
        ),
    ):
        manager.update_subscription("sub-1")
        import time

        time.sleep(0.3)

    assert batch_calls == [], "inspect_batch must NOT be called for > AUTO_INSPECT_LIMIT servers"
    ctx.subscriptions.update.assert_called_once()


def test_inspect_batch_concurrency_limit_is_three():
    """The batch pipeline must never spawn more than 3 concurrent checks."""
    from src.services.server_inspector import ServerInspector

    assert ServerInspector.CONCURRENCY_LIMIT == 3


def test_cancel_all_inspections_cancels_tasks():
    """cancel_all_inspections cancels every tracked task and signals completion."""
    from src.core.event_bus import TOPIC_INSPECTION_BATCH_COMPLETED
    from src.services.server_inspector import ServerInspector

    received = []
    event_bus.subscribe(TOPIC_INSPECTION_BATCH_COMPLETED, lambda d: received.append(d))
    try:
        inspector = ServerInspector()
        task_a = MagicMock()
        task_a.done.return_value = False
        task_b = MagicMock()
        task_b.done.return_value = False
        inspector._active_tasks.add(task_a)
        inspector._active_tasks.add(task_b)

        inspector.cancel_all_inspections()

        task_a.cancel.assert_called()
        task_b.cancel.assert_called()
        assert not inspector._active_tasks
        assert received and received[-1].get("canceled") is True
    finally:
        event_bus.unsubscribe(TOPIC_INSPECTION_BATCH_COMPLETED, lambda d: received.append(d))


def test_inspect_sync_skips_when_canceled():
    """Once canceled, _inspect_sync must not publish inspecting events."""
    from src.services.server_inspector import ServerInspector

    received = []
    event_bus.subscribe(TOPIC_SERVER_INSPECTING, lambda d: received.append(d))
    try:
        inspector = ServerInspector()
        inspector._cancel_event.set()

        inspector._inspect_sync({"id": "p1", "config": {"outbounds": []}})

        assert received == [], "canceled inspection must not start sweeps"
    finally:
        event_bus.unsubscribe(TOPIC_SERVER_INSPECTING, lambda d: received.append(d))
