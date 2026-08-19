"""Tests for the single-publisher contract + EngineEvent typed envelope.

ConnectionManager is the ONLY publisher of TOPIC_CONNECTION_STATE_CHANGED.
Every _emit_event call publishes EXACTLY ONCE (mapped, blocked, or UI-only
events), and the payload is an EngineEvent envelope.
"""

from __future__ import annotations

import importlib

import pytest

from src.core.event_bus import TOPIC_CONNECTION_STATE_CHANGED, EngineEvent
from src.core.fsm.connection_fsm import ConnectionFSM, ConnectionState


@pytest.fixture
def cm_and_fsm(monkeypatch):
    """Build a ConnectionManager stub + private FSM (same trick as the mapping tests)."""
    from src.core.connection_manager import ConnectionManager

    cm = ConnectionManager.__new__(ConnectionManager)
    cm._reconnect_event_listener = None
    cm._monitoring = None
    cm._health_monitor = None

    fsm = ConnectionFSM()
    fsm_module = importlib.import_module("src.core.fsm.connection_fsm")
    monkeypatch.setattr(fsm_module, "connection_fsm", fsm)
    return cm, fsm


def _set_state(fsm: ConnectionFSM, state: ConnectionState) -> None:
    fsm.transition_to(state, force=True)


def test_publish_exactly_once_for_mapped_event(monkeypatch):
    """A mapped event (connecting) publishes TOPIC_CONNECTION_STATE_CHANGED once."""
    from src.core.event_bus import event_bus

    cm, fsm = _cm_fsm(monkeypatch)
    _set_state(fsm, ConnectionState.DISCONNECTED)

    counts = {"n": 0}

    def handler(data):
        counts["n"] += 1

    event_bus.subscribe(TOPIC_CONNECTION_STATE_CHANGED, handler)
    try:
        cm._emit_event("connecting")
    finally:
        event_bus.unsubscribe(TOPIC_CONNECTION_STATE_CHANGED, handler)

    assert counts["n"] == 1, f"expected exactly 1 publish, got {counts['n']}"


def test_publish_exactly_once_for_unmapped_event(monkeypatch):
    """A UI-only event (reconnecting — no FSM mapping) still publishes once."""
    from src.core.event_bus import event_bus

    cm, fsm = _cm_fsm(monkeypatch)
    _set_state(fsm, ConnectionState.CONNECTED)

    counts = {"n": 0}

    def handler(data):
        counts["n"] += 1

    event_bus.subscribe(TOPIC_CONNECTION_STATE_CHANGED, handler)
    try:
        cm._emit_event("reconnecting")
    finally:
        event_bus.unsubscribe(TOPIC_CONNECTION_STATE_CHANGED, handler)

    assert counts["n"] == 1, f"expected exactly 1 publish, got {counts['n']}"


def test_publish_payload_is_engine_event(monkeypatch):
    """The published payload is an EngineEvent envelope with the expected shape."""
    from src.core.event_bus import event_bus

    cm, fsm = _cm_fsm(monkeypatch)
    # Reach CONNECTED legally so the transition is not blocked
    _set_state(fsm, ConnectionState.DISCONNECTED)
    fsm.transition_to(ConnectionState.STARTING)
    fsm.transition_to(ConnectionState.PREPARING)

    received = []

    def handler(data):
        received.append(data)

    event_bus.subscribe(TOPIC_CONNECTION_STATE_CHANGED, handler)
    try:
        cm._emit_event("connected", {"profile": "x"})
    finally:
        event_bus.unsubscribe(TOPIC_CONNECTION_STATE_CHANGED, handler)

    assert len(received) == 1
    ev = received[0]
    assert isinstance(ev, EngineEvent)
    assert ev.event_name == "connected"
    assert ev.source == "connection_manager"
    assert ev.payload["event"] == "connected"
    assert ev.payload["data"] == {"profile": "x"}
    assert ev.payload["state"] == "connected"
    assert ev.ts > 0


def test_engine_event_to_dict_roundtrip():
    ev = EngineEvent(event_name="connected", source="test", payload={"a": 1})
    d = ev.to_dict()
    assert d["event_name"] == "connected"
    assert d["source"] == "test"
    assert d["payload"] == {"a": 1}
    assert "ts" in d


def test_fsm_is_pure_no_bus_publish(monkeypatch):
    """ConnectionFSM.transition_to must NOT publish to the bus (pure)."""
    from src.core.event_bus import event_bus

    counts = {"n": 0}

    def handler(data):
        counts["n"] += 1

    event_bus.subscribe(TOPIC_CONNECTION_STATE_CHANGED, handler)
    try:
        fsm = ConnectionFSM()
        fsm.transition_to(ConnectionState.STARTING)
    finally:
        event_bus.unsubscribe(TOPIC_CONNECTION_STATE_CHANGED, handler)

    assert counts["n"] == 0, "pure FSM must not publish to the bus"


def test_dead_topics_removed():
    """TOPIC_FSM_STATE_CHANGED + unused EVENT_* constants must be gone."""
    import src.core.event_bus as eb

    assert not hasattr(eb, "TOPIC_FSM_STATE_CHANGED"), "dead topic must be deleted"
    for dead in (
        "EVENT_CONNECT_REQUESTED",
        "EVENT_PREPARING_STARTED",
        "EVENT_CONNECTED",
        "EVENT_STOPPING_STARTED",
        "EVENT_ERROR",
        "EVENT_DISCONNECT_REQUESTED",
    ):
        assert not hasattr(eb, dead), f"{dead} must be deleted"
    # The real core facts stay
    assert hasattr(eb, "EVENT_CORE_CRASHED")
    assert hasattr(eb, "EVENT_CORE_PROCESS_STOPPED")


def _cm_fsm(monkeypatch):
    from src.core.connection_manager import ConnectionManager

    cm = ConnectionManager.__new__(ConnectionManager)
    cm._reconnect_event_listener = None
    cm._monitoring = None
    cm._health_monitor = None

    fsm = ConnectionFSM()
    fsm_module = importlib.import_module("src.core.fsm.connection_fsm")
    monkeypatch.setattr(fsm_module, "connection_fsm", fsm)
    return cm, fsm
