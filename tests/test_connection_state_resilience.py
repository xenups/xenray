"""Comprehensive offline regression suite for Connection State Resilience and Recovery.

Tests all 24 failure/recovery scenarios in an entirely offline, mocked environment:
- Zero real host networking calls (no socket, no ping, no HTTP, no DNS)
- Zero external process launches (mocked services and orchestrator)
- Deterministic FSM lifecycle, session invalidation, and UI synchronization.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.core.connection_manager import ConnectionManager
from src.core.event_bus import (
    EVENT_CORE_CRASHED,
    EVENT_CORE_PROCESS_STOPPED,
    TOPIC_CONNECTION_STATE_CHANGED,
    EngineEvent,
    EventBus,
)
from src.core.fsm.connection_fsm import ConnectionFSM, ConnectionState
from src.services.monitoring.auto_reconnect_service import AutoReconnectService, MonitorSignal
from src.ui.handlers.connection_notification_handler import (
    ConnectionNotificationHandler,
    NotificationConnectionState,
)
from src.ui.handlers.reconnect_event_handler import ReconnectEventHandler
from src.ui.pages.dashboard_page import DashboardPage


# =============================================================================
# Test Fixtures & Helpers
# =============================================================================

@pytest.fixture
def isolated_fsm():
    """Independent FSM instance for test isolation."""
    return ConnectionFSM()


@pytest.fixture
def isolated_bus():
    """Independent EventBus instance."""
    return EventBus()


@pytest.fixture
def mock_cm(isolated_fsm, isolated_bus, monkeypatch):
    """ConnectionManager with isolated mocks and state."""
    cm = ConnectionManager.__new__(ConnectionManager)
    cm._state_lock = threading.Lock()
    cm._reconnect_lock = threading.Lock()
    cm._current_connection = None
    cm._session_id = 0
    cm._reconnect_event_listener = None
    cm._orchestrator = MagicMock()
    cm._monitoring = MagicMock()
    cm._health_monitor = MagicMock()
    cm._app_context = MagicMock()

    import importlib
    fsm_mod = importlib.import_module("src.core.fsm.connection_fsm")
    monkeypatch.setattr(fsm_mod, "connection_fsm", isolated_fsm)

    bus_mod = importlib.import_module("src.core.event_bus")
    monkeypatch.setattr(bus_mod, "event_bus", isolated_bus)

    return cm


def _set_fsm_state(fsm: ConnectionFSM, state: ConnectionState) -> None:
    fsm.transition_to(state, force=True)


# =============================================================================
# 1-24 Regression Scenarios
# =============================================================================

def test_01_normal_vpn_connection(mock_cm, isolated_fsm):
    """Scenario 1: Normal VPN connection transitions STARTING -> PREPARING -> CONNECTED."""
    _set_fsm_state(isolated_fsm, ConnectionState.DISCONNECTED)
    assert not isolated_fsm.is_connected

    mock_cm._emit_event("connecting")
    assert isolated_fsm.state == ConnectionState.PREPARING

    mock_cm._emit_event("connected", {"connected_at": 100.0})
    assert isolated_fsm.state == ConnectionState.CONNECTED
    assert isolated_fsm.is_connected
    assert not isolated_fsm.is_degraded


def test_02_temporary_physical_internet_loss_with_healthy_existing_tunnel(mock_cm, isolated_fsm):
    """Scenario 2: Temporary physical Internet loss: CONNECTED -> DEGRADED (session intact)."""
    _set_fsm_state(isolated_fsm, ConnectionState.CONNECTED)
    mock_cm._current_connection = {"file": "config.json", "mode": "vpn", "xray_pid": 1001}
    mock_cm._session_id = 1

    # Active monitor emits connectivity_lost
    mock_cm._emit_event("connectivity_lost")

    assert isolated_fsm.state == ConnectionState.DEGRADED
    assert isolated_fsm.is_connected  # Logical connection and tunnel remain alive!
    assert isolated_fsm.is_degraded


def test_03_temporary_internet_loss_does_not_produce_reconnect_failed():
    """Scenario 3: When physical uplink is down, AutoReconnectService emits degradation, NOT reconnect_failed."""
    emitter = Mock()
    connect_fn = Mock()
    svc = AutoReconnectService(
        network_validator=Mock(),
        config_loader=Mock(return_value=({}, None)),
        connection_tester=Mock(),
        connect_fn=connect_fn,
        event_emitter=emitter,
        internet_check=lambda conn: False,  # Physical uplink is down
    )
    svc.start_session(42)

    conn = {"file": "test.json", "mode": "vpn"}
    res = svc.handle_failure(conn, 42)

    assert res is False
    # Must NOT emit reconnect_failed
    for call_args in emitter.call_args_list:
        event_name = call_args[0][0]
        assert event_name != "reconnect_failed", "Temporary internet loss must not emit reconnect_failed!"

    # Must emit failure_detected and connectivity_degraded
    emitter.assert_any_call("connectivity_degraded", {"reason": "no_internet"})
    # Must not attempt to connect when internet is known to be offline
    connect_fn.assert_not_called()


def test_04_temporary_internet_loss_does_not_trigger_reset_ui_disconnected():
    """Scenario 4: Temporary Internet loss does not call reset_ui_disconnected()."""
    cm = Mock()
    handler = ReconnectEventHandler(cm)
    reset_ui_mock = Mock()
    toast_mock = Mock()
    status_mock = Mock()
    ui_helper = Mock(call=lambda fn: fn())

    handler.setup(
        ui_helper=ui_helper,
        toast=toast_mock,
        status_display=status_mock,
        connection_button=Mock(),
        systray=Mock(),
        update_horizon_glow_callback=Mock(),
        is_running_setter=Mock(),
        profile_manager_is_running_setter=Mock(),
        monitoring_service_is_running_setter=Mock(),
        reset_ui_callback=reset_ui_mock,
    )

    # Receive reconnect_failed with no_internet
    handler._on_event("reconnect_failed", {"reason": "no_internet"})
    reset_ui_mock.assert_not_called()

    # Receive connectivity_degraded with no_internet
    handler._on_event("connectivity_degraded", {"reason": "no_internet"})
    reset_ui_mock.assert_not_called()


def test_05_running_engine_remains_logically_active_during_network_degradation(mock_cm, isolated_fsm):
    """Scenario 5: Running engine remains logically active and session is preserved during degradation."""
    mock_cm._current_connection = {"file": "config.json", "mode": "vpn", "xray_pid": 9999}
    mock_cm._session_id = 5
    _set_fsm_state(isolated_fsm, ConnectionState.CONNECTED)

    mock_cm._emit_event("connectivity_lost")

    assert mock_cm._session_id == 5
    assert mock_cm._current_connection is not None
    assert mock_cm._current_connection["xray_pid"] == 9999
    assert isolated_fsm.is_connected


def test_06_internet_recovery_restores_connected_when_session_healthy(mock_cm, isolated_fsm):
    """Scenario 6: Internet recovery restores CONNECTED state when session is healthy."""
    _set_fsm_state(isolated_fsm, ConnectionState.DEGRADED)
    mock_cm._current_connection = {"file": "config.json", "mode": "vpn"}
    mock_cm._session_id = 5

    mock_cm._emit_event("connectivity_restored")

    assert isolated_fsm.state == ConnectionState.CONNECTED
    assert isolated_fsm.is_connected
    assert not isolated_fsm.is_degraded


def test_07_recovery_does_not_restart_xray_unnecessarily():
    """Scenario 7: Self-healed recovery does not restart Xray or call connect_fn."""
    connect_fn = Mock()
    signal_emitter = Mock()
    svc = AutoReconnectService(
        network_validator=Mock(),
        config_loader=Mock(return_value=({"outbounds": []}, None)),
        connection_tester=Mock(),
        connect_fn=connect_fn,
        event_emitter=Mock(),
        internet_check=lambda conn: True,
        signal_emitter=signal_emitter,
    )
    svc.start_session(10)

    # Core recovered check returns True
    svc._check_core_recovered = Mock(return_value=True)

    conn = {"file": "server.json", "mode": "vpn"}
    res = svc.handle_failure(conn, 10)

    assert res is True
    connect_fn.assert_not_called()
    signal_emitter.assert_called_with(MonitorSignal.ACTIVE_RESTORED, {})


def test_08_recovery_does_not_spawn_duplicate_processes(mock_cm):
    """Scenario 8: Network recovery does not invoke establish_connection or spawn new processes."""
    mock_cm._current_connection = {"file": "vpn.json", "mode": "vpn"}
    mock_cm._session_id = 1
    mock_cm._orchestrator.establish_connection = Mock()

    mock_cm._emit_event("connectivity_restored")

    mock_cm._orchestrator.establish_connection.assert_not_called()


def test_09_genuine_xray_process_termination_is_detected(mock_cm, isolated_fsm):
    """Scenario 9: Genuine Xray process crash triggers session hard-reset and disconnected event."""
    _set_fsm_state(isolated_fsm, ConnectionState.CONNECTED)
    mock_cm._current_connection = {"file": "vpn.json", "mode": "vpn", "xray_pid": 1234}
    mock_cm._session_id = 3
    mock_cm._app_context.settings.get_auto_reconnect_enabled = Mock(return_value=False)

    mock_cm._handle_core_crash(payload={"engine": "xray", "pid": 1234})

    assert mock_cm._current_connection is None
    assert mock_cm._session_id == 0
    assert isolated_fsm.state == ConnectionState.DISCONNECTED


def test_10_genuine_singbox_termination_is_detected(mock_cm, isolated_fsm):
    """Scenario 10: Genuine Sing-box process crash in TUN mode triggers session hard-reset."""
    _set_fsm_state(isolated_fsm, ConnectionState.CONNECTED)
    mock_cm._current_connection = {"file": "vpn.json", "mode": "vpn", "singbox_pid": 5678}
    mock_cm._session_id = 4
    mock_cm._app_context.settings.get_auto_reconnect_enabled = Mock(return_value=False)

    mock_cm._handle_core_crash(payload={"engine": "singbox", "pid": 5678})

    assert mock_cm._current_connection is None
    assert mock_cm._session_id == 0
    assert isolated_fsm.state == ConnectionState.DISCONNECTED


def test_11_tunnel_failure_with_core_running_not_mistaken_for_healthy():
    """Scenario 11: Tunnel failure (uplink OK, but core/proxy dead) proceeds to full reconnect."""
    connect_fn = Mock(return_value=True)
    svc = AutoReconnectService(
        network_validator=Mock(),
        config_loader=Mock(return_value=({}, None)),
        connection_tester=Mock(),
        connect_fn=connect_fn,
        event_emitter=Mock(),
        internet_check=lambda conn: True,  # Uplink is healthy
    )
    svc.start_session(1)
    svc._check_core_recovered = Mock(return_value=False)  # Core did NOT recover
    svc.STABILIZATION_BUFFER = 0.01

    conn = {"file": "config.json", "mode": "vpn"}
    res = svc.handle_failure(conn, 1)

    assert res is True
    connect_fn.assert_called_once()


def test_12_genuine_remote_vpn_server_failure_activates_reconnect_behavior():
    """Scenario 12: Genuine remote VPN failure with working internet executes reconnect attempt."""
    connect_fn = Mock(return_value=True)
    emitter = Mock()
    svc = AutoReconnectService(
        network_validator=Mock(),
        config_loader=Mock(return_value=({}, None)),
        connection_tester=Mock(),
        connect_fn=connect_fn,
        event_emitter=emitter,
        internet_check=lambda conn: True,
    )
    svc.start_session(2)
    svc._check_core_recovered = Mock(return_value=False)
    svc.STABILIZATION_BUFFER = 0.01

    conn = {"file": "remote_server.json", "mode": "vpn"}
    svc.handle_failure(conn, 2)

    emitter.assert_any_call("reconnecting", {})
    connect_fn.assert_called_once_with("remote_server.json", "vpn", conn)


def test_13_dns_failure_does_not_automatically_imply_process_termination(mock_cm, isolated_fsm):
    """Scenario 13: DNS resolution failure / active probe drop does not kill active processes."""
    _set_fsm_state(isolated_fsm, ConnectionState.CONNECTED)
    mock_cm._current_connection = {"file": "vpn.json", "mode": "vpn", "xray_pid": 4321}
    mock_cm._session_id = 9

    # DNS failure causes connectivity degradation
    mock_cm._emit_event("connectivity_degraded", {"reason": "dns_timeout"})

    assert isolated_fsm.state == ConnectionState.DEGRADED
    assert mock_cm._current_connection["xray_pid"] == 4321
    assert mock_cm._session_id == 9


def test_14_repeated_network_interruptions_do_not_cause_state_thrashing(mock_cm, isolated_fsm):
    """Scenario 14: Repeated cycles of network loss and recovery do not thrash FSM or strand states."""
    _set_fsm_state(isolated_fsm, ConnectionState.CONNECTED)
    mock_cm._current_connection = {"file": "vpn.json", "mode": "vpn"}

    for _ in range(5):
        mock_cm._emit_event("connectivity_lost")
        assert isolated_fsm.state == ConnectionState.DEGRADED
        assert isolated_fsm.is_connected

        mock_cm._emit_event("connectivity_restored")
        assert isolated_fsm.state == ConnectionState.CONNECTED
        assert isolated_fsm.is_connected


def test_15_out_of_order_events_do_not_overwrite_newer_state(mock_cm, isolated_fsm):
    """Scenario 15: Out-of-order 'connected' event after session is STOPPING is blocked."""
    _set_fsm_state(isolated_fsm, ConnectionState.STOPPING)

    # Late connected from previous session arriving in STOPPING
    mock_cm._emit_event("reconnected")

    assert isolated_fsm.state == ConnectionState.STOPPING


def test_16_duplicate_recovery_events_are_idempotent(mock_cm, isolated_fsm):
    """Scenario 16: Duplicate connectivity_restored events are idempotent."""
    _set_fsm_state(isolated_fsm, ConnectionState.DEGRADED)

    mock_cm._emit_event("connectivity_restored")
    gen1 = isolated_fsm.state_generation
    assert isolated_fsm.state == ConnectionState.CONNECTED

    # Duplicate call
    mock_cm._emit_event("connectivity_restored")
    assert isolated_fsm.state == ConnectionState.CONNECTED
    # Generation remains identical on no-op
    assert isolated_fsm.state_generation == gen1


def test_17_stale_workers_cannot_change_current_session():
    """Scenario 17: Workers targeting older session IDs are discarded at checkpoints."""
    connect_fn = Mock()
    svc = AutoReconnectService(
        network_validator=Mock(),
        config_loader=Mock(return_value=({}, None)),
        connection_tester=Mock(),
        connect_fn=connect_fn,
        event_emitter=Mock(),
        internet_check=lambda conn: True,
    )
    svc.start_session(10)  # Current session is 10

    # Old worker targeting session 9
    res = svc.handle_failure({"file": "old.json"}, session_id=9)

    assert res is False
    connect_fn.assert_not_called()


def test_18_concurrent_reconnect_attempts_are_controlled(mock_cm):
    """Scenario 18: Reconnection lock prevents concurrent overlapping interface reconnect workers."""
    mock_cm._session_id = 1
    mock_cm._current_connection = {"file": "vpn.json", "mode": "vpn"}
    mock_cm._reconnect_lock.acquire()  # Simulate lock held by another thread

    # Must be safely skipped
    mock_cm._handle_network_interface_changed()
    mock_cm._monitoring.handle_failure.assert_not_called()

    mock_cm._reconnect_lock.release()


def test_19_dashboard_state_agrees_with_authoritative_fsm():
    """Scenario 19: DashboardPage maintains is_connected=True for DEGRADED and CONNECTED."""
    page = DashboardPage.__new__(DashboardPage)
    page._is_connected = False
    page._is_connecting = False
    page._is_disconnecting = False
    page._wave_visualizer = Mock()
    page._server_card = Mock()
    page._connection_button = Mock()
    page._status_display = Mock()
    page._timer_display = Mock()
    page._logs_drawer_component = Mock()

    # Event: connected
    page._apply_connection_event({"event": "connected", "data": {"connected_at": 10.0}})
    assert page._is_connected is True

    # Event: connectivity_degraded
    page._apply_connection_event({"event": "connectivity_degraded", "data": {}})
    assert page._is_connected is True

    # FSM state: degraded
    page._apply_fsm_state_event({"state": "degraded"})
    assert page._is_connected is True

    # Event: connectivity_restored
    page._apply_connection_event({"event": "connectivity_restored", "data": {}})
    assert page._is_connected is True


def test_20_tray_and_notification_agree_with_dashboard(isolated_bus):
    """Scenario 20: No unexpected disconnect notification during temporary network drop with no_internet."""
    mock_notify = Mock()
    handler = ConnectionNotificationHandler(
        selected_profile_getter=lambda: {"name": "TestProfile"},
        notify_fn=mock_notify,
        bus=isolated_bus,
    )
    handler.start()

    # 1. Establish connection
    handler.handle_connected("TestProfile")
    assert mock_notify.call_count == 1
    mock_notify.reset_mock()

    # 2. Degraded event with reason='no_internet'
    isolated_bus.publish(
        TOPIC_CONNECTION_STATE_CHANGED,
        EngineEvent(
            event_name="reconnect_failed",
            source="connection_manager",
            payload={"event": "reconnect_failed", "data": {"reason": "no_internet"}},
        ),
    )

    # Must NOT dispatch unexpected disconnect notification!
    mock_notify.assert_not_called()
    assert handler._state == NotificationConnectionState.CONNECTED
    handler.cleanup()


def test_21_latency_monitoring_does_not_start_because_of_false_disconnected(isolated_fsm, monkeypatch):
    """Scenario 21: Latency monitor trigger_single_check is blocked when FSM is CONNECTED or DEGRADED."""
    from src.ui.handlers.latency_monitor_handler import LatencyMonitorHandler

    lm = LatencyMonitorHandler.__new__(LatencyMonitorHandler)
    lm._selected_profile_getter = Mock(return_value={"id": "prof1", "config": {}})
    lm._connection_button = Mock()
    lm._ui_helper = Mock()
    lm.run_active_ping_sync = Mock()

    import importlib
    fsm_mod = importlib.import_module("src.core.fsm.connection_fsm")
    monkeypatch.setattr(fsm_mod, "connection_fsm", isolated_fsm)

    # In CONNECTED state
    _set_fsm_state(isolated_fsm, ConnectionState.CONNECTED)
    lm.trigger_single_check()
    lm.run_active_ping_sync.assert_not_called()

    # In DEGRADED state
    _set_fsm_state(isolated_fsm, ConnectionState.DEGRADED)
    lm.trigger_single_check()
    lm.run_active_ping_sync.assert_not_called()


def test_22_manual_user_disconnection_still_behaves_correctly(mock_cm, isolated_fsm):
    """Scenario 22: User manual disconnect while DEGRADED cleanly transitions DEGRADED -> STOPPING -> DISCONNECTED."""
    _set_fsm_state(isolated_fsm, ConnectionState.DEGRADED)

    mock_cm._emit_event("disconnecting")
    assert isolated_fsm.state == ConnectionState.STOPPING

    mock_cm._emit_event("disconnected")
    assert isolated_fsm.state == ConnectionState.DISCONNECTED
    assert not isolated_fsm.is_connected


def test_23_core_startup_failure_still_reaches_appropriate_error_state(mock_cm, isolated_fsm):
    """Scenario 23: Startup failure from STARTING or PREPARING reaches ERROR."""
    _set_fsm_state(isolated_fsm, ConnectionState.STARTING)
    mock_cm._emit_event("connect_failed")
    assert isolated_fsm.state == ConnectionState.ERROR

    _set_fsm_state(isolated_fsm, ConnectionState.PREPARING)
    mock_cm._emit_event("connect_failed")
    assert isolated_fsm.state == ConnectionState.ERROR


def test_24_reconnection_failure_is_represented_accurately(mock_cm, isolated_fsm):
    """Scenario 24: Real reconnect failure (connect_failed) transitions to ERROR."""
    _set_fsm_state(isolated_fsm, ConnectionState.CONNECTED)

    mock_cm._emit_event("reconnect_failed", {"reason": "connect_failed"})

    assert isolated_fsm.state == ConnectionState.ERROR
    assert not isolated_fsm.is_connected

