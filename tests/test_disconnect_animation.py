"""Tests for the disconnect lifecycle wiring.

Verifies that the existing red "Disconnecting" animation is invoked when the FSM
enters STOPPING / the user clicks Disconnect, persists until teardown completes,
and is cleanly replaced by "Ready for Flight" on DISCONNECTED.
"""

import threading
from unittest.mock import MagicMock, patch

# Imported first to pre-warm the UI package graph (avoids the pre-existing
# server_list <-> chain_builder_page circular import when a pages module is the
# first UI import in the process). Same pattern as test_ui_views_and_services.py.
from src.ui.components.common.toast import ToastManager  # noqa: F401

from src.core.connection_manager import ConnectionManager
from src.core.event_bus import event_bus
from src.core.fsm.connection_fsm import ConnectionState, connection_fsm
from src.ui.handlers.connection_handler import ConnectionHandler
from src.ui.helpers.ui_thread_helper import UIThreadHelper
from src.ui.main_window import MainWindow


# ---------------------------------------------------------------------------
# ConnectionHandler: disconnect click invokes the red animation
# ---------------------------------------------------------------------------


def _bare_connection_handler() -> ConnectionHandler:
    handler = ConnectionHandler(
        connection_manager=MagicMock(),
        app_context=MagicMock(),
        network_stats=MagicMock(),
    )
    handler._ui_helper = MagicMock()
    return handler


def test_show_disconnecting_ui_invokes_button_red_animation():
    """Disconnect must invoke ConnectionButton.set_disconnecting (red pulse)."""
    handler = _bare_connection_handler()
    handler._connection_button = MagicMock()
    handler._status_display = MagicMock()
    handler._update_horizon_glow_callback = MagicMock()

    handler._show_disconnecting_ui()

    handler._ui_helper.call.assert_any_call(handler._connection_button.set_disconnecting)
    handler._ui_helper.call.assert_any_call(handler._status_display.set_disconnecting)


def test_disconnect_entry_point_triggers_red_animation():
    """The public disconnect() entry point fires the red animation immediately."""
    handler = _bare_connection_handler()
    handler._connection_button = MagicMock()
    handler._status_display = MagicMock()
    handler._update_horizon_glow_callback = MagicMock()
    handler._is_running_getter = lambda: True

    with patch("threading.Thread.start"):
        handler.disconnect()

    handler._ui_helper.call.assert_any_call(handler._connection_button.set_disconnecting)


# ---------------------------------------------------------------------------
# ConnectionManager: EVENT_CORE_PROCESS_STOPPED must not cut the red pulse short
# ---------------------------------------------------------------------------


def _bare_connection_manager() -> ConnectionManager:
    cm = ConnectionManager.__new__(ConnectionManager)
    cm._state_lock = threading.Lock()
    cm._current_connection = {"mode": "vpn", "xray_pid": 1111, "singbox_pid": 2222}
    cm._session_id = 42
    cm._reconnect_event_listener = None
    cm._monitoring = MagicMock()
    cm._health_monitor = MagicMock()
    cm._emit_event = MagicMock()
    return cm


def _orchestrator_with(xray_running: bool, singbox_running: bool) -> MagicMock:
    orchestrator = MagicMock()

    def _service(running: bool):
        svc = MagicMock()
        svc.is_running = lambda: running
        return svc

    orchestrator._xray_service = _service(xray_running)
    orchestrator._singbox_service = _service(singbox_running)
    return orchestrator


def test_process_stopped_waits_for_both_engines_in_vpn_mode():
    """In dual-engine (TUN/VPN) mode the FSM must NOT complete on the first engine.

    If Singbox stops while Xray is still tearing down, the red disconnecting
    animation must keep rendering.
    """
    cm = _bare_connection_manager()
    cm._orchestrator = _orchestrator_with(xray_running=True, singbox_running=False)

    prev_state = connection_fsm.state
    connection_fsm.transition_to(ConnectionState.STOPPING, force=True)
    try:
        cm._handle_core_process_stopped({"engine": "singbox", "pid": 2222})
        assert connection_fsm.state == ConnectionState.STOPPING
    finally:
        connection_fsm.transition_to(prev_state, force=True)
        event_bus.clear()


def test_process_stopped_completes_when_both_engines_stopped():
    """Once BOTH engines are stopped the FSM may complete to DISCONNECTED."""
    cm = _bare_connection_manager()
    cm._orchestrator = _orchestrator_with(xray_running=False, singbox_running=False)

    prev_state = connection_fsm.state
    connection_fsm.transition_to(ConnectionState.STOPPING, force=True)
    try:
        cm._handle_core_process_stopped({"engine": "xray", "pid": 1111})
        assert connection_fsm.state == ConnectionState.DISCONNECTED
    finally:
        connection_fsm.transition_to(prev_state, force=True)
        event_bus.clear()


def test_process_stopped_completes_in_proxy_mode():
    """Proxy mode: singbox service exists but never ran, so xray stop completes it."""
    cm = _bare_connection_manager()
    cm._orchestrator = _orchestrator_with(xray_running=False, singbox_running=False)

    prev_state = connection_fsm.state
    connection_fsm.transition_to(ConnectionState.STOPPING, force=True)
    try:
        cm._handle_core_process_stopped({"engine": "singbox", "pid": None})
        assert connection_fsm.state == ConnectionState.DISCONNECTED
    finally:
        connection_fsm.transition_to(prev_state, force=True)
        event_bus.clear()


# ---------------------------------------------------------------------------
# MainWindow._sync_dashboard_connection_state: FSM-aware, preserves DISCONNECTING
# ---------------------------------------------------------------------------


def _bare_main_window() -> MainWindow:
    mw = MainWindow.__new__(MainWindow)
    mw._is_running = False
    mw._connecting = False
    mw._selected_profile = None
    mw._stitch_dashboard_view = MagicMock()
    mw._stitch_statistics_view = MagicMock()
    mw._nav_sidebar = MagicMock()
    return mw


def test_sync_preserves_disconnecting_while_fsm_stopping():
    """While FSM is STOPPING the sync must keep the red DISCONNECTING state."""
    mw = _bare_main_window()

    prev_state = connection_fsm.state
    connection_fsm.transition_to(ConnectionState.STOPPING, force=True)
    try:
        mw._sync_dashboard_connection_state()
        mw._stitch_dashboard_view.set_connection_state.assert_called_once_with(
            is_connected=False,
            is_connecting=False,
            is_disconnecting=True,
        )
    finally:
        connection_fsm.transition_to(prev_state, force=True)
        event_bus.clear()


def test_sync_ready_for_flight_after_disconnected():
    """Once the FSM reaches DISCONNECTED the sync returns the button to idle."""
    mw = _bare_main_window()

    prev_state = connection_fsm.state
    connection_fsm.transition_to(ConnectionState.DISCONNECTED, force=True)
    try:
        mw._sync_dashboard_connection_state()
        mw._stitch_dashboard_view.set_connection_state.assert_called_once_with(
            is_connected=False,
            is_connecting=False,
            is_disconnecting=False,
        )
    finally:
        connection_fsm.transition_to(prev_state, force=True)
        event_bus.clear()


# ---------------------------------------------------------------------------
# UIThreadHelper: must not drop updates scheduled from the Flet event loop
# ---------------------------------------------------------------------------


def test_ui_thread_helper_runs_inline_when_already_on_loop():
    """On the event loop run_task cannot be scheduled; the update runs inline."""

    class FakePage:
        def __init__(self):
            self.updates = []

        def run_task(self, fn):
            raise RuntimeError("Cannot call run_coroutine_threadsafe() from a running event loop")

        def update(self):
            self.updates.append("update")

    page = FakePage()
    helper = UIThreadHelper(page)
    captured = []

    helper.call(lambda: captured.append("ran"), update_page=True)

    assert captured == ["ran"]
    assert page.updates == ["update"]


def test_ui_thread_helper_schedules_off_loop():
    """From a background thread the update is scheduled via page.run_task."""

    class FakePage:
        def __init__(self):
            self.scheduled = []

        def run_task(self, fn):
            self.scheduled.append(fn)
            return None

    page = FakePage()
    helper = UIThreadHelper(page)
    helper.call(lambda: None)

    assert len(page.scheduled) == 1
