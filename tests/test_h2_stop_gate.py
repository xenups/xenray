"""Tests for HIGH-priority audit fixes H1/H2/H3.

- H2: ConnectionManager._handle_core_process_stopped must NOT flip the FSM to
  DISCONNECTED on the first stop event in dual-engine mode — only once every
  running engine has actually reported stop.
- H3: RouteManagerService cleanup must be idempotent & crash-safe (failed
  removals keep tracking, list not mutated mid-iteration).
"""

import threading
from unittest.mock import Mock

import pytest

from src.core.connection_manager import ConnectionManager
from src.core.fsm.connection_fsm import ConnectionFSM, ConnectionState


class _Ev:
    """Minimal servicelike object exposing is_running() the way the manager reads it."""

    def __init__(self, running):
        self._running = running

    def is_running(self):
        return self._running


class _Eng:
    def __init__(self, running=False):
        self._running = running

    def is_running(self):
        return self._running


@pytest.fixture
def cm_h2(monkeypatch):
    cm = ConnectionManager.__new__(ConnectionManager)
    cm._state_lock = threading.Lock()
    cm._current_connection = None
    cm._session_id = 0
    cm._pending_stop_engines = set()
    cm._monitoring = None
    cm._health_monitor = None
    cm._reconnect_event_listener = None

    fsm = ConnectionFSM()

    import importlib

    fsm_module = importlib.import_module("src.core.fsm.connection_fsm")
    monkeypatch.setattr(fsm_module, "connection_fsm", fsm)

    # orchestrator with two engines both "running" -> _running_orchestrator_engines = {xray, singbox}
    orch = Mock()
    orch._xray_service = _Eng(running=True)
    orch._singbox_service = _Eng(running=True)
    cm._orchestrator = orch
    return cm, fsm, orch


def _fsm_stop(fsm):
    fsm.transition_to(ConnectionState.STOPPING, force=True)


def test_h2_single_stop_event_does_not_prematurely_disconnect(cm_h2):
    """Dual-engine: after the first stop (xray done, singbox still running)
    the FSM must stay STOPPING — the sibling engine's is_running() is still True."""
    cm, fsm, orch = cm_h2
    _fsm_stop(fsm)

    cm._handle_core_process_stopped({"engine": "xray", "pid": 1})

    assert fsm.state == ConnectionState.STOPPING  # still waiting for singbox
    assert not cm._all_expected_engines_stopped()


def test_h2_all_stop_events_flip_to_disconnected(cm_h2):
    """Both engines fully stopped -> FSM reaches DISCONNECTED."""
    cm, fsm, orch = cm_h2
    _fsm_stop(fsm)

    # xray stops: its engine becomes not-running, singbox still running
    orch._xray_service._running = False
    cm._handle_core_process_stopped({"engine": "xray", "pid": 1})
    assert fsm.state == ConnectionState.STOPPING

    # singbox stops too: both now stopped
    orch._singbox_service._running = False
    cm._handle_core_process_stopped({"engine": "singbox", "pid": 2})

    assert fsm.state == ConnectionState.DISCONNECTED


def test_h2_noop_outside_stopping(cm_h2):
    """Outside STOPPING the handler must not touch the FSM."""
    cm, fsm, orch = cm_h2
    fsm.transition_to(ConnectionState.CONNECTED, force=True)

    cm._handle_core_process_stopped({"engine": "xray", "pid": 1})

    assert fsm.state == ConnectionState.CONNECTED
