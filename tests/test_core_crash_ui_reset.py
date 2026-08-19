"""Tests verifying the core-crash teardown pipeline resets FSM/session/UI deterministically.

Covers:
- DashboardPage reacting to raw ConnectionFSM events (ERROR from a core crash).
- ConnectionManager hard-resetting the session on EVENT_CORE_CRASHED.
- ConnectionHandler generation token preventing a stale disconnect task from
  clobbering a newly started connection's CONNECTING UI.
"""

import threading
from unittest.mock import MagicMock, patch

from src.core.connection_manager import ConnectionManager
from src.core.event_bus import event_bus
from src.core.fsm.connection_fsm import ConnectionState, connection_fsm
from src.ui.handlers.connection_handler import ConnectionHandler
from src.ui.pages.dashboard_page import DashboardPage


def _make_dashboard() -> DashboardPage:
    return DashboardPage(
        on_toggle_click=lambda e: None,
        on_change_server_click=lambda e: None,
    )


def test_fsm_error_event_resets_button_to_disconnected():
    """FSM ERROR (core crash) must reset the UI even without an 'event' key."""
    page = _make_dashboard()
    try:
        page.set_connection_state(is_connected=True)
        assert page._toggle_button._state == "connected"

        page._on_connection_state_event(
            {
                "old_state": "connected",
                "new_state": "error",
                "state": "error",
                "generation": 5,
                "payload": {"reason": "core_crashed", "engine": "singbox"},
            }
        )

        assert page._toggle_button._state == "disconnected"
        assert page._is_connected is False
    finally:
        page.set_connection_state(is_connected=False)
        event_bus.clear()


def test_fsm_disconnected_event_resets_button():
    """FSM DISCONNECTED must reset the button like an explicit disconnect."""
    page = _make_dashboard()
    try:
        page.set_connection_state(is_connected=True)

        page._on_connection_state_event(
            {
                "old_state": "stopping",
                "new_state": "disconnected",
                "state": "disconnected",
                "generation": 6,
            }
        )

        assert page._toggle_button._state == "disconnected"
        assert page._is_connected is False
    finally:
        page.set_connection_state(is_connected=False)
        event_bus.clear()


def test_fsm_connected_and_preparing_map_to_ui_states():
    """FSM transitions STARTING/PREPARING/CONNECTED drive the button reactively."""
    page = _make_dashboard()
    try:
        page._on_connection_state_event(
            {
                "old_state": "disconnected",
                "new_state": "starting",
                "state": "starting",
                "generation": 1,
            }
        )
        assert page._toggle_button._state == "connecting"

        page._on_connection_state_event(
            {
                "old_state": "starting",
                "new_state": "preparing",
                "state": "preparing",
                "generation": 2,
            }
        )
        assert page._toggle_button._state == "connecting"

        page._on_connection_state_event(
            {
                "old_state": "preparing",
                "new_state": "connected",
                "state": "connected",
                "generation": 3,
            }
        )
        assert page._toggle_button._state == "connected"
    finally:
        page.set_connection_state(is_connected=False)
        event_bus.clear()


def test_legacy_event_shape_still_handled():
    """ConnectionManager-shaped payloads (with 'event' key) keep working."""
    page = _make_dashboard()
    try:
        page._on_connection_state_event({"event": "connecting", "data": {}})
        assert page._toggle_button._state == "connecting"

        page._on_connection_state_event({"event": "connected", "data": {"connected_at": 1.0}})
        assert page._toggle_button._state == "connected"

        page._on_connection_state_event({"event": "disconnected", "data": {}})
        assert page._toggle_button._state == "disconnected"
    finally:
        page.set_connection_state(is_connected=False)
        event_bus.clear()


# ---------------------------------------------------------------------------
# ConnectionManager session hard-reset on EVENT_CORE_CRASHED
# ---------------------------------------------------------------------------


def _bare_connection_manager(real_emit: bool = False) -> ConnectionManager:
    cm = ConnectionManager.__new__(ConnectionManager)
    cm._state_lock = threading.Lock()
    cm._current_connection = {"mode": "vpn", "xray_pid": 1111, "singbox_pid": 2222}
    cm._session_id = 42
    cm._monitoring = MagicMock()
    cm._health_monitor = MagicMock()
    cm._reconnect_event_listener = None
    if not real_emit:
        cm._emit_event = MagicMock()
    return cm


def test_handle_core_crash_invalidates_session_and_emits_disconnected():
    """On EVENT_CORE_CRASHED the session is invalidated and DISCONNECTED is emitted."""
    cm = _bare_connection_manager()

    cm._handle_core_crash({"crashed_engine": "singbox", "pid": 2222})

    assert cm._current_connection is None
    assert cm._session_id == 0
    cm._monitoring.stop.assert_called_once()
    cm._health_monitor.stop_monitoring.assert_called_once()
    cm._emit_event.assert_called_once_with(
        "disconnected",
        {
            "reason": "core_crashed",
            "crash_payload": {"crashed_engine": "singbox", "pid": 2222},
        },
    )


def test_handle_core_crash_ignored_without_active_session():
    """A late/stale crash event must never tear down a session that no longer exists."""
    cm = _bare_connection_manager()
    cm._current_connection = None
    cm._session_id = 0

    cm._handle_core_crash({"crashed_engine": "singbox", "pid": 2222})

    cm._emit_event.assert_not_called()
    cm._monitoring.stop.assert_not_called()


def test_handle_core_crash_drives_global_fsm_to_disconnected():
    """Full crash path: FSM ends DISCONNECTED so the button returns to 'Ready for Flight'."""
    cm = _bare_connection_manager(real_emit=True)

    prev_state = connection_fsm.state
    connection_fsm.transition_to(ConnectionState.CONNECTED, force=True)
    try:
        cm._handle_core_crash({"crashed_engine": "xray", "pid": 1111})

        assert cm._current_connection is None
        assert cm._session_id == 0
        assert connection_fsm.state == ConnectionState.DISCONNECTED
    finally:
        connection_fsm.transition_to(prev_state, force=True)
        event_bus.clear()


def test_handle_core_process_stopped_transitions_stopping_to_disconnected():
    """EVENT_CORE_PROCESS_STOPPED completes a STOPPING -> DISCONNECTED transition."""
    cm = _bare_connection_manager()

    prev_state = connection_fsm.state
    connection_fsm.transition_to(ConnectionState.STOPPING, force=True)
    try:
        cm._handle_core_process_stopped({"engine": "xray", "pid": 1111})
        assert connection_fsm.state == ConnectionState.DISCONNECTED
    finally:
        connection_fsm.transition_to(prev_state, force=True)
        event_bus.clear()


def test_handle_core_process_stopped_noop_outside_stopping():
    """Outside STOPPING the FSM must not be forced by a single engine's stop event."""
    cm = _bare_connection_manager()

    prev_state = connection_fsm.state
    connection_fsm.transition_to(ConnectionState.CONNECTED, force=True)
    try:
        cm._handle_core_process_stopped({"engine": "xray", "pid": 1111})
        assert connection_fsm.state == ConnectionState.CONNECTED
    finally:
        connection_fsm.transition_to(prev_state, force=True)
        event_bus.clear()


# ---------------------------------------------------------------------------
# ConnectionHandler generation token: stale disconnect reset must be cancelled
# ---------------------------------------------------------------------------


def _bare_connection_handler() -> ConnectionHandler:
    handler = ConnectionHandler(
        connection_manager=MagicMock(),
        app_context=MagicMock(),
        network_stats=MagicMock(),
    )
    handler._generation = 0
    handler._is_running_getter = lambda: True
    handler._set_running_state = MagicMock()
    handler._stop_network_stats = MagicMock()
    handler._connection_manager.disconnect = MagicMock(return_value=True)
    return handler


def test_disconnect_task_skips_stale_reset_when_superseded():
    """A new connect during the disconnect animation must cancel the stale UI reset.

    This is the regression that corrupted button text/animations and skipped the
    initial connect steps on disconnect->reconnect.
    """
    handler = _bare_connection_handler()
    calls = []
    handler._ui_call = lambda cb: calls.append(cb)

    # A newer user action (connect) bumps the generation while the disconnect
    # task is sleeping to render the disconnecting animation.
    def _bump_generation_after_disconnect():
        handler._generation += 1

    handler._connection_manager.disconnect.side_effect = _bump_generation_after_disconnect

    with patch("time.sleep"):
        handler._disconnect_task()

    assert not any(cb == handler.reset_ui_disconnected for cb in calls)


def test_disconnect_task_still_resets_when_not_superseded():
    """Without a superseding action the trailing reset still runs."""
    handler = _bare_connection_handler()
    calls = []
    handler._ui_call = lambda cb: calls.append(cb)

    with patch("time.sleep"):
        handler._disconnect_task()

    assert any(cb == handler.reset_ui_disconnected for cb in calls)
