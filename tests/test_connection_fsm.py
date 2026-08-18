"""Unit tests for ConnectionFSM (Central Event-Driven Finite State Machine)."""

import pytest

from src.core.fsm.connection_fsm import ConnectionFSM, ConnectionState


@pytest.fixture
def fsm():
    return ConnectionFSM()


def test_fsm_initial_state(fsm):
    assert fsm.state == ConnectionState.DISCONNECTED
    assert not fsm.is_connected
    assert not fsm.is_busy
    assert fsm.state_generation == 0


def test_valid_state_transitions(fsm):
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


def test_invalid_state_transition_blocked(fsm):
    # DISCONNECTED -> CONNECTED directly is INVALID and must be blocked
    assert not fsm.transition_to(ConnectionState.CONNECTED)
    assert fsm.state == ConnectionState.DISCONNECTED


def test_defensive_disconnect_flow_from_disconnected(fsm):
    """The engine emits disconnecting->disconnected even when idle. The FSM must
    accept DISCONNECTED -> STOPPING -> DISCONNECTED without warning (defensive
    stop) — this is what ConnectionManager.disconnect() always does."""
    assert fsm.transition_to(ConnectionState.STOPPING)
    assert fsm.state == ConnectionState.STOPPING
    assert fsm.transition_to(ConnectionState.DISCONNECTED)
    assert fsm.state == ConnectionState.DISCONNECTED


def test_defensive_disconnect_flow_from_pinging(fsm):
    """A disconnect during the pre-connection ping check also resolves cleanly."""
    assert fsm.transition_to(ConnectionState.PINGING)
    assert fsm.transition_to(ConnectionState.STOPPING)
    assert fsm.state == ConnectionState.STOPPING
    assert fsm.transition_to(ConnectionState.DISCONNECTED)
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


def test_pinging_state_lifecycle(fsm):
    """PINGING is a valid pre-connection state: enter from DISCONNECTED, exit to
    STARTING (connect clicked) or DISCONNECTED (ping completed, idle)."""
    # DISCONNECTED -> PINGING (initial latency check begins)
    assert fsm.transition_to(ConnectionState.PINGING)
    assert fsm.state == ConnectionState.PINGING

    # PINGING -> STARTING (user clicked Connect mid-ping)
    assert fsm.transition_to(ConnectionState.STARTING)
    assert fsm.state == ConnectionState.STARTING


def test_pinging_returns_to_disconnected_on_ping_done(fsm):
    """A completed ping (no click) must return cleanly to IDLE (DISCONNECTED)."""
    assert fsm.transition_to(ConnectionState.PINGING)
    assert fsm.state == ConnectionState.PINGING

    assert fsm.transition_to(ConnectionState.DISCONNECTED)
    assert fsm.state == ConnectionState.DISCONNECTED


def test_pinging_is_not_busy(fsm):
    """PINGING is a pre-connection (idle-inspecting) state — NOT a connecting
    state, so is_busy stays False (the UI can still react to clicks)."""
    fsm.transition_to(ConnectionState.PINGING)
    assert fsm.state == ConnectionState.PINGING
    assert not fsm.is_busy


def test_cannot_jump_from_pinging_to_connected(fsm):
    """PINGING -> CONNECTED directly is INVALID and must be blocked."""
    assert fsm.transition_to(ConnectionState.PINGING)
    assert not fsm.transition_to(ConnectionState.CONNECTED)
    assert fsm.state == ConnectionState.PINGING


def test_cannot_jump_from_pinging_to_preparing(fsm):
    """PINGING -> PREPARING directly is INVALID and must be blocked.

    The latency check must be exited explicitly (via STARTING for a connect
    click, or DISCONNECTED when the ping completes). ConnectionManager routes
    "connecting" through STARTING first, so this strictness never strands the
    FSM — it protects the invariant that PINGING is always left deliberately.
    """
    assert fsm.transition_to(ConnectionState.PINGING)
    assert not fsm.transition_to(ConnectionState.PREPARING)
    assert fsm.state == ConnectionState.PINGING


def test_error_recovers_to_starting_for_direct_restart(fsm):
    """ERROR -> STARTING must work for an immediate retry (connect click)."""
    assert fsm.transition_to(ConnectionState.STARTING)
    assert fsm.transition_to(ConnectionState.ERROR)
    assert fsm.transition_to(ConnectionState.STARTING)
    assert fsm.state == ConnectionState.STARTING


def test_error_cannot_jump_directly_to_preparing(fsm):
    """ERROR -> PREPARING directly is INVALID — the strict chain is
    ERROR -> STARTING -> PREPARING (ConnectionManager routes through it)."""
    assert fsm.transition_to(ConnectionState.ERROR, force=True)
    assert not fsm.transition_to(ConnectionState.PREPARING)
    assert fsm.state == ConnectionState.ERROR


def test_stopping_reaches_disconnected_from_every_entry(fsm):
    """Every state that can enter STOPPING must resolve to DISCONNECTED.

    STOPPING has no self-resolution; the exit is driven by
    EVENT_CORE_PROCESS_STOPPED (dual-engine gate) or the "disconnected"
    event — both must always be accepted.
    """
    for source in (
        ConnectionState.DISCONNECTED,
        ConnectionState.PINGING,
        ConnectionState.STARTING,
        ConnectionState.PREPARING,
        ConnectionState.CONNECTED,
    ):
        assert fsm.transition_to(source, force=True), f"setup to {source.value}"
        assert fsm.transition_to(ConnectionState.STOPPING), f"{source.value} -> STOPPING"
        assert fsm.transition_to(ConnectionState.DISCONNECTED), "STOPPING -> DISCONNECTED"
        assert fsm.state == ConnectionState.DISCONNECTED
