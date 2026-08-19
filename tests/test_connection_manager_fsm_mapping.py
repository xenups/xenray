"""Tests for ConnectionManager._emit_event -> ConnectionFSM transition mapping.

Every engine event string that carries FSM semantics must produce a valid
transition from every state it can legitimately occur in — never a silent
block that strands the FSM. The FSM itself stays strict; the mapper routes
events through the legal chain (e.g. PINGING/ERROR -> STARTING -> PREPARING).
"""

import threading

import pytest

from src.core.connection_manager import ConnectionManager
from src.core.fsm.connection_fsm import ConnectionFSM, ConnectionState


@pytest.fixture
def cm_and_fsm(monkeypatch):
    """Bare ConnectionManager + private FSM with real _emit_event routing.

    ``_emit_event`` imports the module-level ``connection_fsm`` singleton at
    call time, so it is redirected to a private FSM (private EventBus too) —
    the global FSM/bus are never touched by these tests.
    """
    cm = ConnectionManager.__new__(ConnectionManager)
    cm._state_lock = threading.Lock()
    cm._current_connection = None
    cm._session_id = 0
    cm._monitoring = None
    cm._health_monitor = None
    cm._reconnect_event_listener = None

    fsm = ConnectionFSM()
    # ConnectionManager._emit_event does `from src.core.fsm.connection_fsm
    # import ... connection_fsm` at call time — that reads the attribute on
    # the SUBMODULE in sys.modules. The package attribute 'src.core.fsm.
    # connection_fsm' is shadowed by the __init__ re-export of the singleton,
    # so importlib must be used to reach the real module object.
    import importlib

    fsm_module = importlib.import_module("src.core.fsm.connection_fsm")
    monkeypatch.setattr(fsm_module, "connection_fsm", fsm)
    return cm, fsm


def _set_state(fsm: ConnectionFSM, state: ConnectionState) -> None:
    fsm.transition_to(state, force=True)


def test_connecting_during_pinging_routes_through_starting(cm_and_fsm):
    """THE known bug: Connect clicked while the initial ping runs.

    "connecting" must not be blocked from PINGING (which would leave the FSM
    stuck in PINGING forever) — the mapper routes it PINGING -> STARTING ->
    PREPARING so the engine startup proceeds and later events land.
    """
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.PINGING)

    cm._emit_event("connecting")

    assert fsm.state == ConnectionState.PREPARING


def test_connecting_during_pinging_emits_real_starting_transition(cm_and_fsm):
    """The PINGING -> STARTING hop is a real FSM transition (no force), so the
    generation counter advances twice: PINGING -> STARTING -> PREPARING
    (force-set to PINGING = gen 1, then +2)."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.PINGING)
    assert fsm.state_generation == 1

    cm._emit_event("connecting")

    assert fsm.state == ConnectionState.PREPARING
    assert fsm.state_generation == 3


def test_connecting_from_error_restarts_through_starting(cm_and_fsm):
    """Retry after a failure: ERROR -> STARTING -> PREPARING must work."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.ERROR)

    cm._emit_event("connecting")

    assert fsm.state == ConnectionState.PREPARING


def test_connecting_from_disconnected_enters_preparing_directly(cm_and_fsm):
    """Normal connect (no ping): DISCONNECTED -> PREPARING stays direct."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.DISCONNECTED)

    cm._emit_event("connecting")

    assert fsm.state == ConnectionState.PREPARING


def test_connecting_from_preparing_is_idempotent(cm_and_fsm):
    """A duplicate 'connecting' while already PREPARING is a no-op, not an error."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.PREPARING)

    cm._emit_event("connecting")

    assert fsm.state == ConnectionState.PREPARING


def test_reconnect_failed_from_connected_enters_error(cm_and_fsm):
    """A failed auto-reconnect must drive the FSM to ERROR (never stay CONNECTED)."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.CONNECTED)

    cm._emit_event("reconnect_failed", {"reason": "connect_failed"})

    assert fsm.state == ConnectionState.ERROR


def test_reconnect_failed_from_error_stays_error(cm_and_fsm):
    """reconnect_failed arriving while already in ERROR must not break anything."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.ERROR)

    cm._emit_event("reconnect_failed", {"reason": "no_internet"})

    assert fsm.state == ConnectionState.ERROR


def test_connect_failed_enters_error_from_every_connecting_state(cm_and_fsm):
    """connect_failed must land in ERROR from every state a connect can fail from."""
    cm, fsm = cm_and_fsm
    for source in (
        ConnectionState.DISCONNECTED,
        ConnectionState.PINGING,
        ConnectionState.STARTING,
        ConnectionState.PREPARING,
        ConnectionState.ERROR,
    ):
        _set_state(fsm, source)
        cm._emit_event("connect_failed")
        assert fsm.state == ConnectionState.ERROR, f"connect_failed from {source.value}"


def test_disconnecting_from_error_resets_to_disconnected(cm_and_fsm):
    """Defensive stop from ERROR: no teardown to run, so reset to DISCONNECTED
    instead of blocking and leaving the FSM stuck in ERROR."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.ERROR)

    cm._emit_event("disconnecting")

    assert fsm.state == ConnectionState.DISCONNECTED


def test_disconnecting_from_connected_enters_stopping(cm_and_fsm):
    """Normal stop: CONNECTED -> STOPPING (teardown runs, then DISCONNECTED)."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.CONNECTED)

    cm._emit_event("disconnecting")

    assert fsm.state == ConnectionState.STOPPING


def test_disconnected_event_always_reaches_disconnected(cm_and_fsm):
    """The terminal event must resolve to DISCONNECTED from every state."""
    cm, fsm = cm_and_fsm
    for source in (
        ConnectionState.PINGING,
        ConnectionState.STARTING,
        ConnectionState.PREPARING,
        ConnectionState.CONNECTED,
        ConnectionState.STOPPING,
        ConnectionState.ERROR,
    ):
        _set_state(fsm, source)
        cm._emit_event("disconnected")
        assert fsm.state == ConnectionState.DISCONNECTED, f"disconnected from {source.value}"


def test_connected_event_from_preparing_reaches_connected(cm_and_fsm):
    """The normal success path: PREPARING -> CONNECTED."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.PREPARING)

    cm._emit_event("connected", {"connected_at": 1.0})

    assert fsm.state == ConnectionState.CONNECTED


def test_reconnect_after_crash_lands_in_connected(cm_and_fsm):
    """Full reconnect-after-crash path: ERROR -> "connecting" routes through
    STARTING -> PREPARING, then "connected" reaches CONNECTED."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.ERROR)

    cm._emit_event("connecting")
    assert fsm.state == ConnectionState.PREPARING

    cm._emit_event("connected", {"connected_at": 1.0})
    assert fsm.state == ConnectionState.CONNECTED


def test_connected_from_error_is_still_blocked(cm_and_fsm):
    """ERROR -> CONNECTED directly stays blocked (strict FSM): a reconnect must
    pass through "connecting" first. A stray 'connected' in ERROR is dropped by
    the FSM and only broadcast on the EventBus (no silent state corruption)."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.ERROR)

    cm._emit_event("connected", {"connected_at": 1.0})

    assert fsm.state == ConnectionState.ERROR


def test_reconnected_event_from_connected_is_noop(cm_and_fsm):
    """'reconnected' while already CONNECTED must be a harmless no-op (the
    auto-reconnect flow emits 'connected' from the fresh session; a stale
    'reconnected' must never kick the FSM out of CONNECTED)."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.CONNECTED)

    cm._emit_event("reconnected")

    assert fsm.state == ConnectionState.CONNECTED


def test_reconnected_event_from_stopping_is_blocked(cm_and_fsm):
    """STOPPING -> CONNECTED stays blocked: a stopped session cannot be
    resurrected by a stale 'reconnected' event — only a fresh "connecting"
    flow may start a new session."""
    cm, fsm = cm_and_fsm
    _set_state(fsm, ConnectionState.STOPPING)

    cm._emit_event("reconnected")

    assert fsm.state == ConnectionState.STOPPING
