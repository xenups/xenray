"""Tests for auto-reconnect session semantics.

Verifies the contract between AutoReconnectService and ConnectionManager:

1. The reconnect attempt receives the failing connection context so a fresh
   session can be opened (a reconnect is NOT a continuation of the old
   session — it is a brand-new connection attempt).
2. Reconnect failures are still reported against the ORIGINAL (still valid)
   session; successful reconnects let the new session own the "connected"
   event.
"""
from __future__ import annotations

from unittest.mock import Mock

from src.services.monitoring.auto_reconnect_service import AutoReconnectService


def _make_service(connect_fn=None, event_emitter=None, internet_check=None):
    """Build an AutoReconnectService with isolated mocks."""
    return AutoReconnectService(
        network_validator=Mock(),
        config_loader=Mock(return_value=({}, None)),
        connection_tester=Mock(),
        connect_fn=connect_fn or Mock(return_value=True),
        event_emitter=event_emitter or Mock(),
        internet_check=internet_check or (lambda conn: True),
    )


def test_reconnect_connect_fn_receives_connection_context():
    """The connect callback must receive the failing connection dict.

    ConnectionManager._reconnect_internal opens a FRESH session for the
    reconnect, so AutoReconnectService must forward the full connection
    context (file + mode) instead of only file_path/mode.
    """
    connect_fn = Mock(return_value=True)
    emitter = Mock()
    svc = _make_service(connect_fn=connect_fn, event_emitter=emitter)
    svc.start_session(7)

    connection = {"file": "/tmp/x.json", "mode": "vpn", "xray_pid": 1234}
    result = svc.handle_failure(connection, 7)

    assert result is True
    connect_fn.assert_called_once_with("/tmp/x.json", "vpn", connection)


def test_failed_reconnect_emits_reconnect_failed_against_original_session():
    """A failed reconnect stays inside the original session and must emit
    ``reconnect_failed`` (ReconnectEventHandler relies on it to reset UI)."""
    connect_fn = Mock(return_value=False)
    emitter = Mock()
    svc = _make_service(connect_fn=connect_fn, event_emitter=emitter)
    svc.start_session(7)

    connection = {"file": "/tmp/x.json", "mode": "vpn"}
    result = svc.handle_failure(connection, 7)

    assert result is False
    emitter.assert_any_call("reconnecting", {})
    emitter.assert_any_call("reconnect_failed", {"reason": "connect_failed"})


def test_reconnect_does_not_emit_reconnected_after_success():
    """After a successful reconnect the session has moved on (connect() bumps
    the session id). Emitting "reconnected" against the stale id is impossible
    by design — the new session owns the "connected" event."""
    connect_fn = Mock(return_value=True)
    emitter = Mock()
    svc = _make_service(connect_fn=connect_fn, event_emitter=emitter)
    svc.start_session(7)

    connection = {"file": "/tmp/x.json", "mode": "vpn"}
    result = svc.handle_failure(connection, 7)

    assert result is True
    emitted = [call.args[0] for call in emitter.call_args_list]
    assert "reconnected" not in emitted
    assert "reconnecting" in emitted


def test_stale_session_failure_is_ignored():
    """A failure that arrives after the session was invalidated (disconnect /
    stop) must be silently dropped — no events, no reconnect."""
    connect_fn = Mock(return_value=True)
    emitter = Mock()
    svc = _make_service(connect_fn=connect_fn, event_emitter=emitter)
    svc.start_session(7)
    svc.cancel()

    result = svc.handle_failure({"file": "/tmp/x.json", "mode": "vpn"}, 7)

    assert result is False
    connect_fn.assert_not_called()
    emitter.assert_not_called()
