"""Unit tests for DashboardController state transitions and throughput calculations."""

from __future__ import annotations

import time

import pytest

from src.ui.controllers.dashboard_controller import DashboardController, DashboardState


def test_dashboard_controller_initial_state():
    """Test initial state of DashboardController."""
    ctrl = DashboardController()
    assert ctrl.state == DashboardState.DISCONNECTED


def test_dashboard_controller_state_transitions():
    """Test state transitions DISCONNECTED -> CONNECTING -> CONNECTED -> DISCONNECTING."""
    state_history = []

    def on_state_changed(state: DashboardState, label: str):
        state_history.append((state, label))

    ctrl = DashboardController(on_state_changed=on_state_changed)

    # 1. Connecting
    ctrl.set_connection_state(is_connected=False, is_connecting=True)
    assert ctrl.state == DashboardState.CONNECTING
    assert state_history[-1][0] == DashboardState.CONNECTING

    # 2. Connected
    ctrl.set_connection_state(is_connected=True)
    assert ctrl.state == DashboardState.CONNECTED
    assert state_history[-1][0] == DashboardState.CONNECTED

    # 3. Disconnecting
    ctrl.set_connection_state(is_connected=False, is_disconnecting=True)
    assert ctrl.state == DashboardState.DISCONNECTING
    assert state_history[-1][0] == DashboardState.DISCONNECTING

    # 4. Disconnected
    ctrl.set_connection_state(is_connected=False)
    assert ctrl.state == DashboardState.DISCONNECTED
    assert state_history[-1][0] == DashboardState.DISCONNECTED

    ctrl.stop_uptime_timer()


def test_dashboard_controller_deduplicates_same_state_emissions():
    """Re-pushing the same CONNECTING state must not re-fire the state callback.

    The connecting state is emitted both by the handler's ``_set_connecting``
    sync and the EventBus ``connecting`` event — a duplicate would render the
    intermediate status text ("در حال اوج‌گیری" / initializing) twice.
    """
    state_history = []

    def on_state_changed(state: DashboardState, label: str):
        state_history.append(state)

    ctrl = DashboardController(on_state_changed=on_state_changed)

    # Two identical CONNECTING pushes (the duplicate scenario) -> single emission
    ctrl.set_connection_state(is_connected=False, is_connecting=True)
    ctrl.set_connection_state(is_connected=False, is_connecting=True)
    assert state_history == [DashboardState.CONNECTING]
    assert ctrl.state == DashboardState.CONNECTING

    # A real transition still fires exactly once
    ctrl.set_connection_state(is_connected=True)
    assert state_history == [DashboardState.CONNECTING, DashboardState.CONNECTED]

    ctrl.stop_uptime_timer()


def test_dashboard_controller_process_network_stats():
    """Test processing network statistics into formatted KB/s and MB/s strings."""
    stats_history = []

    def on_stats_updated(dl_text: str, ul_text: str, total_bps: float):
        stats_history.append((dl_text, ul_text, total_bps))

    ctrl = DashboardController(on_stats_updated=on_stats_updated)

    # Test KB/s upload speed
    ctrl.process_network_stats(
        rate_str="1.2 MB/s",
        download_bps=1200000.0,
        upload_bps=51200.0,
    )
    assert len(stats_history) == 1
    dl_text, ul_text, total_bps = stats_history[0]
    assert dl_text == "1.2 MB/s"
    assert ul_text == "50.0 KB/s"
    assert total_bps == 1251200.0

    # Test MB/s upload speed
    ctrl.process_network_stats(
        rate_str="5.0 MB/s",
        download_bps=5000000.0,
        upload_bps=2097152.0,
    )
    dl_text, ul_text, total_bps = stats_history[1]
    assert ul_text == "2.0 MB/s"
