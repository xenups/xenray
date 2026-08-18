"""Tests for the monitoring false-pulse fixes (C1-C4).

C1: private/LAN-address guard — dial/timeout lines targeting internal
    addresses must NOT trigger PASSIVE_FAILURE alerts; public targets still
    alert.
C2: debounce — 12 identical same-second matches yield exactly ONE alert.
C3: reconnect_failed leaves the UI/FSM in a consistent error state — the
    ReconnectEventHandler clears the in-flight reconnect flag so a later
    stale "connected" can never be dressed up as a reconnection success.
C4: a single PASSIVE_FAILURE signal produces exactly ONE handle_failure call.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from unittest.mock import Mock

from src.services.monitoring.passive_log_monitor import PassiveLogMonitor
from src.ui.handlers.reconnect_event_handler import ReconnectEventHandler


def _wait_for(condition, timeout: float = 6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def _write(path: str, content: str):
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# C1: private/LAN-address guard
# ---------------------------------------------------------------------------


class TestPrivateTargetGuard:
    """The bug: `dial tcp 172.16.0.2:1688: i/o timeout` is an internal service
    failure, NOT a VPN outage — it must never raise PASSIVE_FAILURE."""

    def test_helper_classifies_private_addresses(self):
        for line in [
            "dial tcp 172.16.0.2:1688: i/o timeout",  # the user-log bug line
            "dial tcp 10.0.0.5:80: connect: connection refused",
            "dial tcp 192.168.1.10:443: i/o timeout",
            "dial tcp 127.0.0.1:1080: connection refused",
            "dial tcp 169.254.1.1:53: i/o timeout",
            "dial tcp 100.64.0.1:443: connection timed out",
            "dial tcp 172.31.255.254:22: i/o timeout",
        ]:
            assert PassiveLogMonitor._is_private_target(line), line

    def test_helper_classifies_public_addresses(self):
        for line in [
            "dial tcp 1.1.1.1:443: i/o timeout",
            "dial tcp 8.8.8.8:53: connection refused",
            "dial tcp 172.15.0.1:80: i/o timeout",  # outside 172.16-31
            "dial tcp 172.32.0.1:80: i/o timeout",  # outside 172.16-31
            "dial tcp 100.63.255.255:80: i/o timeout",  # outside 100.64/10
            "dial tcp 100.72.1.1:80: i/o timeout",  # 100.64/10 -> private
        ]:
            # classify_public: only the last one (100.64/10) is private
            expected_private = "100.72" in line
            assert PassiveLogMonitor._is_private_target(line) is expected_private, line

    def test_helper_rejects_false_positives_inside_longer_tokens(self):
        """Whole-token matching: a private-looking substring inside a public IP
        (e.g. 192.168.1.5 inside 1.2.192.168.1.5) must NOT count as private."""
        assert not PassiveLogMonitor._is_private_target("dial tcp 1.2.192.168.1.5:443: i/o timeout")
        assert not PassiveLogMonitor._is_private_target("dial tcp 255.255.10.0.1:443: i/o timeout")

    def test_private_dial_line_does_not_alert(self):
        """The exact user-log line: internal dial must be silently skipped."""
        monitor = PassiveLogMonitor(log_files=[])
        callback = Mock()
        monitor._on_failure = callback
        monitor.start()
        try:
            monitor._process_line(
                "2026/05/26 13:05:25 ERROR connection: open connection to 172.16.0.2:1688 "
                "using outbound/direct: dial tcp 172.16.0.2:1688: i/o timeout",
                source="singbox",
            )
            time.sleep(0.3)
            callback.assert_not_called()
        finally:
            monitor.stop()

    def test_public_dial_line_alerts(self):
        """Same failure shape but a PUBLIC target is a genuine VPN failure."""
        monitor = PassiveLogMonitor(log_files=[])
        callback = Mock()
        monitor._on_failure = callback
        monitor.start()
        try:
            monitor._process_line(
                "2026/05/26 13:05:25 ERROR connection: open connection to 1.1.1.1:443 "
                "using outbound/proxy[proxy]: dial tcp 1.1.1.1:443: i/o timeout",
                source="singbox",
            )
            assert _wait_for(lambda: callback.call_count >= 1), "public dial must alert"
            callback.assert_called_once()
            payload = callback.call_args[0][0]
            assert payload["source"] == "singbox"
        finally:
            monitor.stop()

    def test_public_connection_refused_alerts(self):
        monitor = PassiveLogMonitor(log_files=[])
        callback = Mock()
        monitor._on_failure = callback
        monitor.start()
        try:
            monitor._process_line(
                "2026/05/26 13:05:25 [Warning] dial tcp 1.1.1.1:443: connect: connection refused",
                source="xray",
            )
            assert _wait_for(lambda: callback.call_count >= 1), "public refused must alert"
            callback.assert_called_once()
        finally:
            monitor.stop()

    def test_private_connection_refused_skipped(self):
        monitor = PassiveLogMonitor(log_files=[])
        callback = Mock()
        monitor._on_failure = callback
        monitor.start()
        try:
            monitor._process_line(
                "2026/05/26 13:05:25 [Warning] dial tcp 192.168.1.50:8080: connect: connection refused",
                source="xray",
            )
            time.sleep(0.3)
            callback.assert_not_called()
        finally:
            monitor.stop()

    def test_non_dial_keywords_still_alert_with_private_ips_in_line(self):
        """The guard applies ONLY to dial-type keywords: an engine failure line
        (fatal:, failed to start, ...) must still alert even if it happens to
        mention a private address."""
        monitor = PassiveLogMonitor(log_files=[])
        callback = Mock()
        monitor._on_failure = callback
        monitor.start()
        try:
            monitor._process_line(
                "2026/05/26 13:05:25 [FATAL] fatal: failed to create tun: 10.0.0.5: permission denied",
                source="singbox",
            )
            assert _wait_for(lambda: callback.call_count >= 1), "fatal engine failure must alert"
            callback.assert_called_once()
        finally:
            monitor.stop()

    def test_tailer_skips_private_dial_lines(self):
        """End-to-end through the real tailer: 12 identical private-dial lines
        in the log file produce ZERO alerts (and no PASSIVE_FAILURE spam)."""
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "xenray_singbox.log")
            _write(log, "startup ok\n")

            received = []
            monitor = PassiveLogMonitor(
                on_failure_callback=lambda payload: received.append(payload),
                log_files=[log],
            )
            monitor.CHECK_INTERVAL = 0.1
            monitor.start()
            try:
                for _ in range(12):
                    _write(
                        log,
                        "2026/05/26 13:05:25 ERROR connection: open connection to 172.16.0.2:1688 "
                        "using outbound/direct: dial tcp 172.16.0.2:1688: i/o timeout\n",
                    )
                time.sleep(1.2)
                assert received == [], f"private dials must not alert, got {received}"
            finally:
                monitor.stop()


# ---------------------------------------------------------------------------
# C2: debounce — 12 same-second matches yield exactly ONE alert
# ---------------------------------------------------------------------------


def test_debounce_yields_single_alert_for_12_same_second_matches():
    """The log showed 12 identical matches in one second -> must produce ONE
    alert, not 12 (per-source debounce is the duplicate-signal guard)."""
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "xenray_xray.log")
        _write(log, "startup ok\n")

        received = []
        monitor = PassiveLogMonitor(
            on_failure_callback=lambda payload: received.append(payload),
            log_files=[log],
        )
        monitor.CHECK_INTERVAL = 0.05
        monitor.DEBOUNCE_SECONDS = 5.0  # the production value
        monitor.start()
        try:
            for _ in range(12):
                _write(log, "2026/05/26 13:05:25 [Warning] dial tcp 1.1.1.1:443: i/o timeout\n")
            assert _wait_for(lambda: len(received) >= 1), "first alert not detected"
            time.sleep(1.0)  # let any duplicate callbacks land
            assert len(received) == 1, f"expected exactly 1 alert, got {len(received)}"
        finally:
            monitor.stop()


# ---------------------------------------------------------------------------
# C3: reconnect_failed leaves UI/FSM in a consistent error state
# ---------------------------------------------------------------------------


def _make_handler():
    cm = Mock()
    handler = ReconnectEventHandler(cm)
    handler._ui_helper = Mock()
    handler._ui_helper.call.side_effect = lambda fn: fn()  # run UI callbacks inline
    handler._toast = Mock()
    handler._reset_ui_callback = Mock()
    return handler


def test_reconnect_failed_resets_inflight_flag():
    """After reconnect_failed the handler must NOT believe a reconnect is still
    in flight: a stale "connected" from the failed attempt must not be treated
    as a reconnection success (no ERROR -> CONNECTED UI jump)."""
    handler = _make_handler()
    handler._is_reconnecting = True  # simulate reconnecting event seen

    handler._on_event("reconnect_failed", {"reason": "connect_failed"})

    assert handler._is_reconnecting is False
    handler._reset_ui_callback.assert_called_once()
    handler._toast.error.assert_called_once()


def test_stale_connected_after_reconnect_failed_is_not_reconnected():
    """The full sequence: reconnecting -> reconnect_failed -> stale connected
    must leave the UI in the reset/error state — the stale "connected" is a
    normal-connect event (flag cleared), so no reconnected-style UI update."""
    handler = _make_handler()
    connected_calls = {"n": 0}
    handler._handle_reconnected = lambda data: connected_calls.__setitem__("n", connected_calls["n"] + 1)

    handler._on_event("reconnecting", {})
    assert handler._is_reconnecting is True

    handler._on_event("reconnect_failed", {"reason": "no_internet"})
    assert handler._is_reconnecting is False

    handler._on_event("connected", {"connected_at": 1.0})
    assert handler._is_reconnecting is False
    assert connected_calls["n"] == 0, "stale connected must not be treated as reconnected"


def test_reconnect_failed_resets_running_state():
    """reconnect_failed drives the UI to the reset/error state (is_running
    setters + button/status/glow), consistent with FSM -> ERROR."""
    cm = Mock()
    handler = ReconnectEventHandler(cm)
    ui_helper = Mock()
    ui_helper.call.side_effect = lambda fn: fn()  # run UI callbacks inline
    is_running = Mock()
    profile_running = Mock()
    monitoring_running = Mock()
    button = Mock()
    status = Mock()
    glow = Mock()
    handler.setup(
        ui_helper=ui_helper,
        toast=Mock(),
        status_display=status,
        connection_button=button,
        systray=None,
        update_horizon_glow_callback=glow,
        is_running_setter=is_running,
        profile_manager_is_running_setter=profile_running,
        monitoring_service_is_running_setter=monitoring_running,
        reset_ui_callback=Mock(),
    )

    # The main window's _reset_ui_disconnected drives running=False via
    # ConnectionHandler.reset_ui_disconnected (the same path used by
    # disconnect). Lock in that contract at the handler level:
    handler._on_event("reconnect_failed", {"reason": "connect_failed"})
    handler._reset_ui_callback.assert_called_once()

    # And a successful NEW attempt must be able to bring the UI back up:
    handler._on_event("reconnecting", {})
    assert handler._is_reconnecting is True
    handler._on_event("connected", {"connected_at": 1.0})
    assert handler._is_reconnecting is False
    button.set_connected.assert_called_once()


# ---------------------------------------------------------------------------
# C4: no duplicate handle_failure per PASSIVE_FAILURE signal
# ---------------------------------------------------------------------------


def test_single_passive_failure_signal_single_handle_failure():
    """ConnectionManager._handle_signal must call handle_failure EXACTLY ONCE
    per PASSIVE_FAILURE signal (each signal already went through the monitor's
    per-source debounce; a second call would double-trigger reconnect)."""
    import threading as _threading

    from src.core.connection_manager import ConnectionManager
    from src.services.monitoring.signals import MonitorSignal, signal_payload

    cm = ConnectionManager.__new__(ConnectionManager)
    cm._state_lock = _threading.Lock()
    cm._current_connection = {"file": "/tmp/x.json", "mode": "vpn", "session_id": 3}
    cm._session_id = 3
    cm._monitoring = Mock()
    cm._health_monitor = Mock()
    cm._MonitorSignal = MonitorSignal

    cm._handle_signal(
        MonitorSignal.PASSIVE_FAILURE, signal_payload("singbox", line="dial tcp 1.1.1.1:443: i/o timeout")
    )

    cm._monitoring.handle_failure.assert_called_once()
    cm._monitoring.handle_failure.assert_called_once_with(cm._current_connection)


def test_passive_failure_signal_ignored_without_valid_session():
    """No valid session -> the signal is dropped BEFORE reaching handle_failure
    (no reconnect from stale/late signals)."""
    import threading as _threading

    from src.core.connection_manager import ConnectionManager
    from src.services.monitoring.signals import MonitorSignal, signal_payload

    cm = ConnectionManager.__new__(ConnectionManager)
    cm._state_lock = _threading.Lock()
    cm._current_connection = None
    cm._session_id = 0
    cm._monitoring = Mock()
    cm._MonitorSignal = MonitorSignal

    cm._handle_signal(MonitorSignal.PASSIVE_FAILURE, signal_payload("singbox"))

    cm._monitoring.handle_failure.assert_not_called()


def test_direct_outbound_timeout_does_not_alert():
    """C1b: 'dial tcp <public>: i/o timeout' via outbound/direct is a direct-path
    (censorship/network) failure, NOT a VPN tunnel outage — must NOT alert."""
    monitor = PassiveLogMonitor(on_failure_callback=Mock())
    line = (
        "connection: open connection to 149.154.167.220:443 using "
        "outbound/direct[direct]: dial tcp 149.154.167.220:443: i/o timeout"
    )
    monitor._process_line(line, "singbox")
    monitor._on_failure.assert_not_called()


def test_direct_outbound_connection_refused_does_not_alert():
    """C1b: refused via direct outbound also skips (same reasoning)."""
    monitor = PassiveLogMonitor(on_failure_callback=Mock())
    line = (
        "connection: open connection to 8.8.8.8:53 using outbound/direct[direct]: "
        "dial tcp 8.8.8.8:53: connection refused"
    )
    monitor._process_line(line, "singbox")
    monitor._on_failure.assert_not_called()


def test_tunnel_outbound_public_timeout_still_alerts():
    """A timeout on a PUBLIC target through the VPN TUNNEL outbound must alert."""
    monitor = PassiveLogMonitor(log_files=[], on_failure_callback=Mock())
    callback = Mock()
    monitor._on_failure = callback
    monitor.start()
    try:
        line = (
            "connection: open connection to 149.154.167.220:443 using "
            "outbound/proxy[proxy]: dial tcp 149.154.167.220:443: i/o timeout"
        )
        monitor._process_line(line, "singbox")
        assert _wait_for(lambda: callback.call_count >= 1), "tunnel outbound public timeout must alert"
        callback.assert_called_once()
    finally:
        monitor.stop()


def test_is_direct_outbound_helper():
    assert PassiveLogMonitor._is_direct_outbound(
        "connection: open connection to 1.2.3.4:443 using outbound/direct[direct]: dial tcp"
    )
    assert not PassiveLogMonitor._is_direct_outbound(
        "connection: open connection to 1.2.3.4:443 using outbound/proxy[proxy]: dial tcp"
    )
    assert not PassiveLogMonitor._is_direct_outbound("fatal: failed to create tun")
