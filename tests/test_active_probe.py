"""Tests for ActiveConnectivityMonitor — real probe-based detection."""

from __future__ import annotations

import time
from unittest.mock import patch

from src.services.monitoring.active_connectivity_monitor import ActiveConnectivityMonitor


def _wait_for(condition, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_healthy_connection_no_events():
    """When the light probe succeeds every sample, no events are emitted."""
    lost, restored, degraded = [], [], []
    monitor = ActiveConnectivityMonitor(
        socks_port_getter=lambda: 10805,
        on_connectivity_lost=lambda: lost.append(1),
        on_connectivity_restored=lambda: restored.append(1),
        on_connectivity_degraded=lambda: degraded.append(1),
    )
    with patch.object(monitor, "_probe_socks_socket", return_value=True):
        monitor.start(session_id=1)
        try:
            time.sleep(0.5)
            # Several samples with healthy probe
            monitor._check_connectivity()
            monitor._check_connectivity()
            monitor._check_connectivity()
        finally:
            monitor.stop()
    assert lost == [] and restored == [] and degraded == []


def test_light_probe_failure_then_http_ok_no_loss():
    """Light probe fails but HTTP probe succeeds → idle system, NOT lost."""
    lost, restored, degraded = [], [], []
    monitor = ActiveConnectivityMonitor(
        socks_port_getter=lambda: 10805,
        on_connectivity_lost=lambda: lost.append(1),
        on_connectivity_restored=lambda: restored.append(1),
        on_connectivity_degraded=lambda: degraded.append(1),
    )
    # Light probe always fails; HTTP probe always succeeds
    with patch.object(monitor, "_probe_socks_socket", return_value=False):
        with patch.object(monitor, "_verify_connectivity", return_value=True):
            monitor.start(session_id=1)
            try:
                for _ in range(10):
                    monitor._check_connectivity()
            finally:
                monitor.stop()
    assert lost == [], "HTTP probe OK means connection is fine (idle)"


def test_probe_failure_triggers_lost_after_confirmation():
    """Both light AND heavy probes fail repeatedly → ACTIVE_LOST emitted once."""
    lost, restored, degraded = [], [], []
    monitor = ActiveConnectivityMonitor(
        socks_port_getter=lambda: 10805,
        on_connectivity_lost=lambda: lost.append(1),
        on_connectivity_restored=lambda: restored.append(1),
        on_connectivity_degraded=lambda: degraded.append(1),
    )
    with patch.object(monitor, "_probe_socks_socket", return_value=False):
        with patch.object(monitor, "_verify_connectivity", return_value=False):
            monitor.start(session_id=1)
            try:
                for _ in range(10):
                    monitor._check_connectivity()
            finally:
                monitor.stop()
    assert len(lost) == 1, f"Expected exactly 1 LOST event, got {len(lost)}"


def test_restored_emitted_after_recovery():
    """After LOST, a healthy probe emits RESTORED once."""
    lost, restored, degraded = [], [], []
    monitor = ActiveConnectivityMonitor(
        socks_port_getter=lambda: 10805,
        on_connectivity_lost=lambda: lost.append(1),
        on_connectivity_restored=lambda: restored.append(1),
        on_connectivity_degraded=lambda: degraded.append(1),
    )

    # Phase 1: fail repeatedly → LOST
    with patch.object(monitor, "_probe_socks_socket", return_value=False):
        with patch.object(monitor, "_verify_connectivity", return_value=False):
            monitor.start(session_id=1)
            try:
                for _ in range(10):
                    monitor._check_connectivity()
            finally:
                monitor.stop()

    assert len(lost) == 1

    # Phase 2: healthy again → RESTORED
    # NOTE: start() resets _is_connected=True, so we simulate the recovery
    # by checking while the monitor is already running (not after stop).
    with patch.object(monitor, "_probe_socks_socket", return_value=True):
        monitor.start(session_id=2)
        try:
            monitor._is_connected = False  # simulate previous LOST state
            monitor._check_connectivity()
        finally:
            monitor.stop()

    assert len(restored) == 1, f"Expected exactly 1 RESTORED event, got {len(restored)}"
