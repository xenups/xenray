"""Unit tests for TUNProcessWatcher and process crash recovery."""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.services.tun_process_watcher import TUNProcessWatcher


def test_watcher_triggers_crash_callback_on_unexpected_exit(tmp_path):
    log_file = tmp_path / "test.log"
    log_file.write_text("Fatal error: TUN adapter initialization failed\n")

    mock_process = Mock()
    mock_process.pid = 1234
    # Simulate process poll returning exit code 1
    mock_process.poll.return_value = 1

    crash_callback = Mock()

    watcher = TUNProcessWatcher(
        process=mock_process,
        on_crash_callback=crash_callback,
        log_file_path=str(log_file),
        name="TestProcess",
    )

    watcher.start()
    time.sleep(0.7)

    crash_callback.assert_called_once()
    exit_code, snippet = crash_callback.call_args[0]
    assert exit_code == 1
    assert "TUN adapter initialization failed" in snippet


def test_watcher_ignores_intentional_stop(tmp_path):
    log_file = tmp_path / "test.log"
    log_file.write_text("Normal shutdown log\n")

    mock_process = Mock()
    mock_process.pid = 1234
    mock_process.poll.return_value = None

    crash_callback = Mock()

    watcher = TUNProcessWatcher(
        process=mock_process,
        on_crash_callback=crash_callback,
        log_file_path=str(log_file),
        name="TestProcess",
    )

    watcher.start()
    # Mark as intentional stop before process exits
    watcher.stop()
    mock_process.poll.return_value = 0
    time.sleep(0.7)

    crash_callback.assert_not_called()


def test_emergency_disconnect_pipeline():
    mock_app_context = Mock()
    mock_app_context.load_config.return_value = ({}, None)
    mock_app_context.settings.get_proxy_port.return_value = 10808

    from src.core.connection_manager import ConnectionManager

    with patch("src.core.connection_manager.XrayService"):
        with patch("src.services.monitoring.ConnectionMonitoringService"):
            with patch("src.core.connection_manager.ConnectionOrchestrator") as MockOrchestrator:
                orchestrator_instance = MockOrchestrator.return_value
                manager = ConnectionManager(mock_app_context)

                events_emitted = []
                manager.set_reconnect_event_listener(lambda evt, data: events_emitted.append(evt))

                manager._current_connection = {"mode": "vpn", "xray_pid": 9999}
                manager._session_id = 1

                with patch("src.utils.notification_utils.send_os_notification") as mock_notify:
                    manager.handle_emergency_disconnect("TUN process crashed")

                    assert "disconnecting" in events_emitted
                    assert "disconnected" in events_emitted
                    orchestrator_instance.teardown_connection.assert_called_once()
                    mock_notify.assert_called_once()
