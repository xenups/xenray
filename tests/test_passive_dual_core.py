"""Tests for PassiveLogMonitor — dual-core (Xray + sing-box) tailing."""

from __future__ import annotations

import os
import tempfile
import time
from unittest.mock import patch

from src.services.monitoring.passive_log_monitor import PassiveLogMonitor


def _wait_for(condition, timeout: float = 6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def _write(path: str, content: str):
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)


def test_tails_both_core_logs():
    """PassiveLogMonitor must tail BOTH the Xray log and the sing-box TUN log."""
    with tempfile.TemporaryDirectory() as tmp:
        xray_log = os.path.join(tmp, "xenray_xray.log")
        singbox_log = os.path.join(tmp, "xenray_singbox.log")
        # Pre-create both logs
        _write(xray_log, "startup ok\n")
        _write(singbox_log, "startup ok\n")

        received = []
        monitor = PassiveLogMonitor(
            on_failure_callback=lambda payload: received.append(payload),
            log_files=[xray_log, singbox_log],
        )
        monitor.start()
        try:
            # Xray-core warning-level error
            _write(xray_log, "2026-01-01 10:00:00 [Warning] dial tcp 1.2.3.4:443: connect: connection refused\n")
            assert _wait_for(lambda: bool(received)), "Xray log error not detected"
            assert received[0]["source"] == "xray"

            received.clear()
            # Resume immediately: the first alert paused the monitor for the
            # backoff window; without resume the second alert would be swallowed.
            monitor.resume()
            # sing-box TUN error
            _write(singbox_log, "2026-01-01 10:00:01 [WARN] failed to create tun: permission denied\n")
            assert _wait_for(lambda: bool(received)), "sing-box log error not detected"
            assert received[0]["source"] == "singbox"
        finally:
            monitor.stop()


def test_dns_fallback_does_not_trigger_failure():
    """DNS fallback lines are WARNINGS and must never trigger the failure callback."""
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "xenray_xray.log")
        _write(log, "startup ok\n")

        received = []
        monitor = PassiveLogMonitor(
            on_failure_callback=lambda payload: received.append(payload),
            log_files=[log],
        )
        monitor.start()
        try:
            _write(log, "2026-01-01 10:00:00 [Warning] failed to resolve domain example.com\n")
            time.sleep(1.2)
            assert received == [], "DNS fallback must NOT trigger failure callback"
        finally:
            monitor.stop()


def test_healthy_lines_do_not_trigger():
    """Normal warning-level lines (e.g. traffic, info) must not fire alerts."""
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "xenray_xray.log")
        _write(log, "startup ok\n")

        received = []
        monitor = PassiveLogMonitor(
            on_failure_callback=lambda payload: received.append(payload),
            log_files=[log],
        )
        monitor.start()
        try:
            _write(log, "2026-01-01 10:00:00 [Info] accepted connection from 127.0.0.1:50000\n")
            _write(log, "2026-01-01 10:00:01 [Warning] some unrelated warning\n")
            time.sleep(1.2)
            assert received == [], "Healthy lines must not trigger failure"
        finally:
            monitor.stop()


def test_debounce_prevents_flooding():
    """Multiple matching lines within DEBOUNCE_SECONDS produce only ONE alert."""
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "xenray_xray.log")
        _write(log, "startup ok\n")

        received = []
        monitor = PassiveLogMonitor(
            on_failure_callback=lambda payload: received.append(payload),
            log_files=[log],
        )
        monitor.start()
        try:
            # Multiple errors in quick succession
            for _ in range(5):
                _write(log, "2026-01-01 10:00:00 [Warning] connection refused\n")
            time.sleep(1.2)
            assert len(received) == 1, f"Expected exactly 1 alert, got {len(received)}"
        finally:
            monitor.stop()
