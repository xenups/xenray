"""Tests for PassiveLogMonitor — dual-core (Xray + sing-box) tailing."""

from __future__ import annotations

import os
import tempfile
import time

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
            # NOTE (F6): the monitor no longer self-pauses after an alert, so
            # no resume() is needed — the next failure is detected immediately
            # (debounce-per-source only).
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


def test_fatal_config_line_does_not_trigger_alert():
    """F4: a config line containing 'fatal' must NOT fire the failure callback.

    Regression for the false-positive: bare ``"fatal"`` used to match ANY line
    containing the substring, e.g. ``log.level: "fatal"``, causing spurious
    reconnect signals.
    """
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "xenray_singbox.log")
        _write(log, "startup ok\n")

        received = []
        monitor = PassiveLogMonitor(
            on_failure_callback=lambda payload: received.append(payload),
            log_files=[log],
        )
        monitor.start()
        try:
            _write(log, '{"level":"info","msg":"using log level fatal as configured"}\n')
            _write(log, '2026-01-01 10:00:00 [INFO] config: log.level: "fatal"\n')
            time.sleep(1.2)
            assert received == [], f"Config line containing 'fatal' must NOT trigger, got {received}"
        finally:
            monitor.stop()


def test_fatal_failure_line_triggers_alert():
    """F4: a REAL sing-box fatal failure (``fatal:`` prefix) still fires."""
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "xenray_singbox.log")
        _write(log, "startup ok\n")

        received = []
        monitor = PassiveLogMonitor(
            on_failure_callback=lambda payload: received.append(payload),
            log_files=[log],
        )
        monitor.start()
        try:
            _write(log, "2026-01-01 10:00:01 [FATAL] fatal: failed to create tun: permission denied\n")
            assert _wait_for(lambda: bool(received)), "fatal failure line not detected"
            assert received[0]["source"] == "singbox"
        finally:
            monitor.stop()


def test_alerts_not_paused_after_first_failure():
    """F6: after the first alert the monitor stays live — new failures are
    detected immediately instead of being swallowed by a self-pause backoff.

    Regression for the finding that a 5–300s self-pause could blind the
    passive monitor to NEW failures during the reconnect window (leaving zero
    reconnect signals in proxy mode where no active probe runs).
    """
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "xenray_xray.log")
        _write(log, "startup ok\n")

        received = []
        monitor = PassiveLogMonitor(
            on_failure_callback=lambda payload: received.append(payload),
            log_files=[log],
        )
        monitor.DEBOUNCE_SECONDS = 0.1  # short per-source debounce for the test
        monitor.start()
        try:
            _write(log, "2026-01-01 10:00:00 [Warning] dial tcp 1.2.3.4:443: connection refused\n")
            assert _wait_for(lambda: len(received) >= 1), "first alert not detected"
            # No resume() — the monitor must keep scanning.
            _write(log, "2026-01-01 10:00:01 [Warning] dial tcp 1.2.3.4:443: connection refused\n")
            assert _wait_for(lambda: len(received) >= 2), "second alert not detected without resume"
            assert len(received) >= 2
        finally:
            monitor.stop()


def test_callback_executor_is_bounded():
    """F10: failure callbacks go through a single-worker executor, not one
    fresh daemon thread per alert."""
    monitor = PassiveLogMonitor(log_files=[])
    try:
        assert monitor._callback_executor._max_workers == 1
    finally:
        monitor._callback_executor.shutdown(wait=False)
