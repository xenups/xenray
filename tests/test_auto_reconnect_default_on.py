"""Auto-reconnect default-OFF behaviour tests.

Locks in the contract that auto-reconnect is DISABLED BY DEFAULT:

1. SettingsRepository.get_auto_reconnect_enabled() returns False when the
   settings file is absent (default-off) and True only after an explicit enable.
2. ConnectionMonitoringService honors the setting: when auto-reconnect is
   disabled (the default), monitoring does not start, so failures never reach
   the reconnect path.
"""

from __future__ import annotations

from unittest.mock import Mock

from src.repositories.settings_repository import SettingsRepository
from src.services.monitoring import ConnectionMonitoringService


def _make_monitoring_service(app_context, on_reconnect=None, on_reconnect_event=None):
    """Build ConnectionMonitoringService with safe isolated callbacks."""
    return ConnectionMonitoringService(
        app_context=app_context,
        on_signal=Mock(),
        on_reconnect=on_reconnect or Mock(return_value=True),
        on_reconnect_event=on_reconnect_event or Mock(),
    )


class TestAutoReconnectDefaultOff:
    """SettingsRepository: auto-reconnect defaults to OFF."""

    def test_auto_reconnect_defaults_to_false_when_file_absent(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        assert repo.get_auto_reconnect_enabled() is False

    def test_auto_reconnect_false_after_explicit_disable(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        repo.set_auto_reconnect_enabled(False)
        assert repo.get_auto_reconnect_enabled() is False

    def test_auto_reconnect_round_trip(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        repo.set_auto_reconnect_enabled(False)
        assert repo.get_auto_reconnect_enabled() is False
        repo.set_auto_reconnect_enabled(True)
        assert repo.get_auto_reconnect_enabled() is True

    def test_auto_reconnect_default_off_across_instances(self, tmp_path):
        # First instance never writes the file; a fresh instance (new app
        # launch) must still see default-off.
        SettingsRepository(str(tmp_path))
        repo2 = SettingsRepository(str(tmp_path))
        assert repo2.get_auto_reconnect_enabled() is False


class TestMonitoringServiceHonorsAutoReconnect:
    """ConnectionMonitoringService: honors the auto-reconnect setting."""

    def test_monitoring_does_not_start_when_disabled_by_default(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))  # file absent -> default off
        app_context = Mock()
        app_context.settings = repo
        app_context.load_config = Mock(return_value=({}, None))

        service = _make_monitoring_service(app_context)
        assert service.start(session_id=1, mode="vpn") is False

    def test_monitoring_starts_when_explicitly_enabled(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        repo.set_auto_reconnect_enabled(True)
        app_context = Mock()
        app_context.settings = repo
        app_context.load_config = Mock(return_value=({}, None))

        service = _make_monitoring_service(app_context)
        assert service.start(session_id=1, mode="vpn") is True
        service.stop()

    def test_handle_failure_does_not_trigger_reconnect_when_disabled(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        repo.set_auto_reconnect_enabled(False)
        app_context = Mock()
        app_context.settings = repo
        app_context.load_config = Mock(return_value=({}, None))

        on_reconnect = Mock(return_value=True)
        service = _make_monitoring_service(app_context, on_reconnect=on_reconnect)
        assert service.start(session_id=1, mode="vpn") is False

        service.handle_failure({"file": "/tmp/x.json", "mode": "vpn"})

        on_reconnect.assert_not_called()

    def test_handle_failure_does_not_trigger_reconnect_when_off_by_default(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))  # file absent -> default off
        app_context = Mock()
        app_context.settings = repo
        app_context.load_config = Mock(return_value=({}, None))

        on_reconnect = Mock(return_value=True)
        service = _make_monitoring_service(app_context, on_reconnect=on_reconnect)
        assert service.start(session_id=1, mode="vpn") is False

        service.handle_failure({"file": "/tmp/x.json", "mode": "vpn"})

        on_reconnect.assert_not_called()
