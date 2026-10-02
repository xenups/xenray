"""Tests for ReconnectEventHandler._handle_connectivity_restored tray notification."""

from unittest.mock import MagicMock

from src.ui.handlers.reconnect_event_handler import ReconnectEventHandler


class TestConnectivityRestoredTrayNotify:
    def _make_handler(self, systray=None):
        ui_helper = MagicMock()
        ui_helper.call = lambda fn: fn()  # execute the callback inline
        handler = ReconnectEventHandler(connection_manager=MagicMock())
        handler.setup(
            ui_helper=ui_helper,
            toast=MagicMock(),
            status_display=MagicMock(),
            connection_button=MagicMock(),
            systray=systray,
            update_horizon_glow_callback=MagicMock(),
            is_running_setter=MagicMock(),
            profile_manager_is_running_setter=MagicMock(),
            monitoring_service_is_running_setter=MagicMock(),
            reset_ui_callback=MagicMock(),
        )
        return handler

    def test_connectivity_restored_updates_ui_and_notifies_tray(self):
        """Restoration must restore UI state AND dispatch tray notification."""
        systray = MagicMock()
        handler = self._make_handler(systray=systray)

        handler._handle_connectivity_restored({})

        # UI state restored to connected
        handler._is_running_setter.assert_called_with(True)
        handler._profile_manager_is_running_setter.assert_called_with(True)
        handler._monitoring_service_is_running_setter.assert_called_with(True)
        handler._connection_button.set_connected.assert_called_once()
        handler._status_display.set_connected.assert_called_once()

        # Tray notified (update_state + notify) — this is the desktop feedback
        systray.update_state.assert_called_once()
        systray.notify.assert_called_once()

    def test_connectivity_restored_notify_never_breaks_state(self):
        """A tray-notification failure must NOT corrupt the state machine."""
        systray = MagicMock()
        systray.notify.side_effect = RuntimeError("tray dead")
        handler = self._make_handler(systray=systray)

        # Must NOT raise — the exception is swallowed defensively
        handler._handle_connectivity_restored({})

        # State still restored correctly
        handler._is_running_setter.assert_called_with(True)
        handler._connection_button.set_connected.assert_called_once()

    def test_connectivity_restored_without_systray(self):
        """No systray attached — handler still restores UI, skips notify."""
        handler = self._make_handler(systray=None)

        handler._handle_connectivity_restored({})

        handler._connection_button.set_connected.assert_called_once()
        handler._status_display.set_connected.assert_called_once()
