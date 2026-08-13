"""Tests for the logs-off-by-default behaviour (user must Enable tailing)."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.ui.components.logs.log_viewer import LogViewer


def test_log_viewer_starts_off():
    """The log viewer must NOT tail anything at construction."""
    lv = LogViewer("test")
    assert lv.user_enabled is False
    assert lv._log_thread is None
    assert lv._stop_flag is None


def test_connection_handler_skips_auto_start_when_disabled():
    """_start_log_tailing must no-op when the user has not enabled tailing."""
    from src.ui.handlers.connection_handler import ConnectionHandler

    lv = LogViewer("test")
    lv.start_tailing = MagicMock()

    # Build a bare handler (only the log viewer matters for this test)
    handler = ConnectionHandler.__new__(ConnectionHandler)
    handler._log_viewer = lv

    handler._start_log_tailing("vpn")
    lv.start_tailing.assert_not_called()


def test_connection_handler_starts_when_user_enabled():
    """Once the user enabled tailing, connection events may refresh the tailer."""
    from src.ui.handlers.connection_handler import ConnectionHandler

    lv = LogViewer("test")
    lv.user_enabled = True
    lv.start_tailing = MagicMock()

    handler = ConnectionHandler.__new__(ConnectionHandler)
    handler._log_viewer = lv

    handler._start_log_tailing("vpn")
    lv.start_tailing.assert_called_once()


def test_drawer_toggle_sets_user_enabled():
    """Toggling Enable in the drawer flips log_viewer.user_enabled."""
    from src.ui.components.logs.logs_drawer import LogsDrawer

    lv = LogViewer("test")
    lv.start_tailing = MagicMock()
    lv.stop_tailing = MagicMock()

    drawer = LogsDrawer(log_viewer=lv, heartbeat=MagicMock())

    # Simulate the Enable click
    drawer._toggle_tailing(MagicMock(control=MagicMock()))
    assert lv.user_enabled is True
    lv.start_tailing.assert_called_once()

    # Simulate the Disable click
    drawer._toggle_tailing(MagicMock(control=MagicMock()))
    assert lv.user_enabled is False
    lv.stop_tailing.assert_called_once()
