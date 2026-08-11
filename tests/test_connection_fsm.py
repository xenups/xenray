"""Unit tests for ConnectionFSM (Central Event-Driven Finite State Machine)."""

import pytest

from src.core.event_bus import TOPIC_CONNECTION_STATE_CHANGED, EventBus
from src.core.fsm.connection_fsm import ConnectionFSM, ConnectionState


@pytest.fixture
def test_bus():
    bus = EventBus()
    yield bus
    bus.clear()


@pytest.fixture
def fsm(test_bus):
    return ConnectionFSM(bus=test_bus)


def test_fsm_initial_state(fsm):
    assert fsm.state == ConnectionState.DISCONNECTED
    assert not fsm.is_connected
    assert not fsm.is_busy
    assert fsm.state_generation == 0


def test_valid_state_transitions(fsm, test_bus):
    events = []

    def handler(payload):
        events.append(payload)

    test_bus.subscribe(TOPIC_CONNECTION_STATE_CHANGED, handler)

    # DISCONNECTED -> STARTING
    assert fsm.transition_to(ConnectionState.STARTING)
    assert fsm.state == ConnectionState.STARTING
    assert fsm.is_busy
    assert fsm.state_generation == 1

    # STARTING -> PREPARING
    assert fsm.transition_to(ConnectionState.PREPARING)
    assert fsm.state == ConnectionState.PREPARING

    # PREPARING -> CONNECTED
    assert fsm.transition_to(ConnectionState.CONNECTED)
    assert fsm.state == ConnectionState.CONNECTED
    assert fsm.is_connected

    # CONNECTED -> STOPPING
    assert fsm.transition_to(ConnectionState.STOPPING)
    assert fsm.state == ConnectionState.STOPPING

    # STOPPING -> DISCONNECTED
    assert fsm.transition_to(ConnectionState.DISCONNECTED)
    assert fsm.state == ConnectionState.DISCONNECTED
    assert not fsm.is_connected

    assert len(events) == 5


def test_invalid_state_transition_blocked(fsm):
    # DISCONNECTED -> CONNECTED directly is INVALID and must be blocked
    assert not fsm.transition_to(ConnectionState.CONNECTED)
    assert fsm.state == ConnectionState.DISCONNECTED

    # DISCONNECTED -> STOPPING directly is INVALID
    assert not fsm.transition_to(ConnectionState.STOPPING)
    assert fsm.state == ConnectionState.DISCONNECTED


def test_forced_transition_and_reset(fsm):
    # Force jump from DISCONNECTED to CONNECTED
    assert fsm.transition_to(ConnectionState.CONNECTED, force=True)
    assert fsm.state == ConnectionState.CONNECTED

    # Reset
    fsm.reset(error=True)
    assert fsm.state == ConnectionState.ERROR

    fsm.reset(error=False)
    assert fsm.state == ConnectionState.DISCONNECTED


def test_error_state_recovers_to_disconnected_and_restarts(fsm):
    """After a core crash (ERROR) the FSM must recover cleanly to DISCONNECTED
    and be ready for a new flight (DISCONNECTED -> STARTING)."""
    # Reach CONNECTED then crash into ERROR (core crash path)
    assert fsm.transition_to(ConnectionState.STARTING)
    assert fsm.transition_to(ConnectionState.PREPARING)
    assert fsm.transition_to(ConnectionState.CONNECTED)
    assert fsm.transition_to(ConnectionState.ERROR)

    # ERROR -> DISCONNECTED (clean UI reset to "Ready for Flight")
    assert fsm.transition_to(ConnectionState.DISCONNECTED)
    assert fsm.state == ConnectionState.DISCONNECTED
    assert not fsm.is_connected

    # DISCONNECTED -> STARTING (new flight)
    assert fsm.transition_to(ConnectionState.STARTING)
    assert fsm.state == ConnectionState.STARTING
    assert fsm.is_busy
