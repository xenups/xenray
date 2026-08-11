"""Unit tests for EventBus Pub/Sub messaging and handler exception isolation."""

from __future__ import annotations

from src.core.event_bus import EventBus


def test_event_bus_subscribe_publish():
    """Test subscribing to topics and receiving published event payloads."""
    bus = EventBus()
    received = []

    def handler(payload):
        received.append(payload)

    bus.subscribe("profile_changed", handler)
    bus.publish("profile_changed", {"id": "sub-1", "name": "Config A"})

    assert len(received) == 1
    assert received[0]["name"] == "Config A"

    bus.unsubscribe("profile_changed", handler)
    bus.publish("profile_changed", {"id": "sub-2", "name": "Config B"})
    assert len(received) == 1


def test_event_bus_multiple_handlers():
    """Test multiple handlers receiving the same event."""
    bus = EventBus()
    out1 = []
    out2 = []

    bus.subscribe("connection_state", lambda d: out1.append(d))
    bus.subscribe("connection_state", lambda d: out2.append(d))

    bus.publish("connection_state", True)
    assert out1 == [True]
    assert out2 == [True]


def test_event_bus_handler_exception_isolation():
    """Test that an exception in one handler does not break publishing to other handlers."""
    bus = EventBus()
    received = []

    def broken_handler(payload):
        raise RuntimeError("Handler crash")

    def safe_handler(payload):
        received.append(payload)

    bus.subscribe("network_stats", broken_handler)
    bus.subscribe("network_stats", safe_handler)

    # Publish should log exception for broken_handler but still deliver to safe_handler
    bus.publish("network_stats", {"speed": "1.5 MB/s"})
    assert received == [{"speed": "1.5 MB/s"}]
