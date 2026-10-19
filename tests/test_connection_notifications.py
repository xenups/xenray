"""Unit tests for Connection Status Notifications in Xenray.

Tests cover:
- Successful connection -> one success notification (with and without profile name)
- Manual disconnect -> one disconnect notification
- Unexpected connection loss -> one warning notification (core crash, drop, reconnect failed)
- Repeated status checks/events -> no duplicate notifications
- Failed connection attempt -> no false success notification
- Disconnect before successful connection -> no misleading notification
- Reconnection after a drop -> correct notifications for each genuine transition
- Application shutdown -> no spurious notifications
- Fail-soft handling if OS notification raises an error
"""

from unittest.mock import MagicMock

import pytest

from src.core.event_bus import EVENT_CORE_CRASHED, TOPIC_CONNECTION_STATE_CHANGED, EngineEvent, EventBus
from src.ui.handlers.connection_notification_handler import ConnectionNotificationHandler, NotificationConnectionState


class TestConnectionNotificationHandler:
    @pytest.fixture
    def mock_notify(self):
        """Mock OS-level desktop notification dispatch."""
        return MagicMock()

    @pytest.fixture
    def mock_systray(self, mock_notify):
        """Mock SystrayHandler with notify method."""
        systray = MagicMock()
        systray.notify = mock_notify
        return systray

    @pytest.fixture
    def test_bus(self):
        """Isolated EventBus instance for testing."""
        return EventBus()

    @pytest.fixture
    def handler(self, mock_notify, test_bus):
        """Initialized notification handler using mock_notify and test_bus."""
        profile_getter = MagicMock(return_value={"name": "US-Fast", "id": "p1"})
        h = ConnectionNotificationHandler(
            selected_profile_getter=profile_getter,
            notify_fn=mock_notify,
            bus=test_bus,
        )
        h.start()
        return h

    # -------------------------------------------------------------------------
    # 1. Successful connection
    # -------------------------------------------------------------------------

    def test_successful_connection_with_profile_name(self, handler, mock_notify):
        """Successful connection shows desktop notification containing active profile name."""
        res = handler.handle_connected(profile_name="US-Fast")

        assert res is True
        assert handler._state == NotificationConnectionState.CONNECTED
        mock_notify.assert_called_once()
        msg, title = mock_notify.call_args[0]
        assert "US-Fast" in msg
        assert title == "XenRay"

    def test_successful_connection_resolved_from_profile_getter(self, handler, mock_notify):
        """Successful connection resolves profile name from selected_profile_getter if not passed."""
        res = handler.handle_connected(profile_name=None)

        assert res is True
        mock_notify.assert_called_once()
        msg, title = mock_notify.call_args[0]
        assert "US-Fast" in msg

    def test_successful_connection_without_profile_name(self, mock_notify, test_bus):
        """Successful connection shows clean fallback when no profile name is available."""
        h = ConnectionNotificationHandler(
            selected_profile_getter=lambda: None,
            notify_fn=mock_notify,
            bus=test_bus,
        )
        res = h.handle_connected(profile_name=None)

        assert res is True
        mock_notify.assert_called_once()
        msg, title = mock_notify.call_args[0]
        assert msg != ""
        assert title == "XenRay"

    def test_connecting_does_not_show_success_notification(self, handler, mock_notify):
        """Merely initiating connection must not trigger a success notification."""
        handler.handle_connecting()

        assert handler._state == NotificationConnectionState.CONNECTING
        mock_notify.assert_not_called()

    # -------------------------------------------------------------------------
    # 2. Manual disconnection
    # -------------------------------------------------------------------------

    def test_manual_disconnect_shows_one_disconnect_notification(self, handler, mock_notify):
        """Manual disconnection from an active connection shows exactly one disconnect notification."""
        # 1. Connect
        handler.handle_connected(profile_name="US-Fast")
        mock_notify.reset_mock()

        # 2. User initiates disconnect
        handler.handle_disconnecting(is_manual=True)
        assert mock_notify.call_count == 0  # not yet finished

        # 3. Teardown completes
        res = handler.handle_disconnected(is_manual=True)

        assert res is True
        assert handler._state == NotificationConnectionState.DISCONNECTED
        mock_notify.assert_called_once()
        msg, title = mock_notify.call_args[0]
        assert "Disconnected" in msg or "قطع" in msg or "Отключено" in msg or "断开" in msg

    # -------------------------------------------------------------------------
    # 3. Unexpected disconnection
    # -------------------------------------------------------------------------

    def test_unexpected_disconnection_shows_warning_notification(self, handler, mock_notify):
        """Unexpected disconnection drops show a clear unexpected warning message."""
        # 1. Connect
        handler.handle_connected(profile_name="US-Fast")
        mock_notify.reset_mock()

        # 2. Unexpected drop occurs without manual flag
        res = handler.handle_disconnected(is_manual=False)

        assert res is True
        assert handler._state == NotificationConnectionState.DISCONNECTED
        mock_notify.assert_called_once()
        msg, title = mock_notify.call_args[0]
        assert "lost unexpectedly" in msg or "غیرمنتظره" in msg or "неожиданно" in msg or "意外" in msg

    def test_core_crash_triggers_unexpected_warning_notification(self, handler, mock_notify):
        """Core process crash while connected triggers unexpected disconnection warning."""
        # 1. Connect
        handler.handle_connected(profile_name="US-Fast")
        mock_notify.reset_mock()

        # 2. Core crash
        res = handler.handle_unexpected_disconnect(reason="core_crashed")

        assert res is True
        mock_notify.assert_called_once()
        msg, _ = mock_notify.call_args[0]
        assert "unexpectedly" in msg or "غیرمنتظره" in msg or "неожиданно" in msg or "意外" in msg

        # 3. Subsequent disconnected event from teardown does not duplicate
        res_dup = handler.handle_disconnected(is_manual=False, reason="core_crashed")
        assert res_dup is False
        assert mock_notify.call_count == 1

    def test_reconnect_failed_triggers_unexpected_warning_notification(self, handler, mock_notify):
        """Tunnel loss where reconnect fails completely emits unexpected disconnect warning."""
        # 1. Connect
        handler.handle_connected(profile_name="US-Fast")
        mock_notify.reset_mock()

        # 2. Reconnect failed
        res = handler.handle_unexpected_disconnect(reason="reconnect_failed")

        assert res is True
        mock_notify.assert_called_once()

    # -------------------------------------------------------------------------
    # 4. Duplicate prevention
    # -------------------------------------------------------------------------

    def test_repeated_connected_events_do_not_duplicate(self, handler, mock_notify):
        """Repeated connected events while already connected are ignored."""
        # First connection
        assert handler.handle_connected(profile_name="US-Fast") is True
        assert mock_notify.call_count == 1

        # Repeated connected events (polling, telemetry, callbacks)
        assert handler.handle_connected(profile_name="US-Fast") is False
        assert handler.handle_connected(profile_name="US-Fast") is False
        assert mock_notify.call_count == 1

    def test_repeated_disconnect_events_do_not_duplicate(self, handler, mock_notify):
        """Repeated disconnected events while already disconnected are ignored."""
        handler.handle_connected(profile_name="US-Fast")
        mock_notify.reset_mock()

        handler.handle_disconnecting(is_manual=True)
        assert handler.handle_disconnected(is_manual=True) is True
        assert mock_notify.call_count == 1

        # Repeated stops (e.g. dual engine teardown, UI reset callback)
        assert handler.handle_disconnected(is_manual=True) is False
        assert handler.handle_disconnected(is_manual=False) is False
        assert mock_notify.call_count == 1

    # -------------------------------------------------------------------------
    # 5. Failed connection attempt
    # -------------------------------------------------------------------------

    def test_failed_connection_attempt_no_false_success_or_disconnect(self, handler, mock_notify):
        """Failed connection attempt emits neither success nor disconnect notifications."""
        handler.handle_connecting()
        res = handler.handle_connect_failed(reason="invalid_config")

        assert res is False
        assert handler._state == NotificationConnectionState.DISCONNECTED
        mock_notify.assert_not_called()

    # -------------------------------------------------------------------------
    # 6. Disconnect before successful connection
    # -------------------------------------------------------------------------

    def test_disconnect_before_successful_connection_no_notification(self, handler, mock_notify):
        """User cancels/disconnects while connecting — no misleading notification."""
        handler.handle_connecting()
        handler.handle_disconnecting(is_manual=True)
        res = handler.handle_disconnected(is_manual=True)

        assert res is False
        assert handler._state == NotificationConnectionState.DISCONNECTED
        mock_notify.assert_not_called()

    def test_disconnect_when_already_idle_no_notification(self, handler, mock_notify):
        """Disconnecting when never connected emits no notifications."""
        res = handler.handle_disconnected(is_manual=True)
        assert res is False
        mock_notify.assert_not_called()

    # -------------------------------------------------------------------------
    # 7. Reconnection after a drop
    # -------------------------------------------------------------------------

    def test_reconnection_after_drop_genuine_transitions(self, handler, mock_notify):
        """Drop followed by recovery emits one warning on drop and one success on reconnect."""
        # 1. Initial successful connection
        handler.handle_connected(profile_name="US-Fast")
        assert mock_notify.call_count == 1
        msg1, _ = mock_notify.call_args[0]
        assert "US-Fast" in msg1

        # 2. Unexpected drop
        handler.handle_unexpected_disconnect(reason="drop")
        assert mock_notify.call_count == 2
        msg2, _ = mock_notify.call_args[0]
        assert "unexpectedly" in msg2 or "غیرمنتظره" in msg2 or "неожиданно" in msg2 or "意外" in msg2

        # 3. Reconnect attempt starts
        handler.handle_connecting()
        assert mock_notify.call_count == 2

        # 4. Reconnect succeeds
        handler.handle_connected(profile_name="US-Fast")
        assert mock_notify.call_count == 3
        msg3, _ = mock_notify.call_args[0]
        assert "US-Fast" in msg3

    def test_reconnect_failure_after_established_connection_reports_loss_without_duplicates(self, handler, mock_notify):
        """Sequence: connected -> connecting -> connect_failed -> reconnect_failed emits single warning."""
        # 1. Connection established
        handler.handle_connected(profile_name="US-Fast")
        assert mock_notify.call_count == 1
        mock_notify.reset_mock()

        # 2. Connection drops and auto-reconnect emits connecting
        handler.handle_connecting()
        assert mock_notify.call_count == 0

        # 3. Connection attempt fails -> reports loss of established session
        res_fail = handler.handle_connect_failed(reason="timeout")
        assert res_fail is True
        assert mock_notify.call_count == 1
        msg, _ = mock_notify.call_args[0]
        assert "unexpectedly" in msg or "غیرمنتظره" in msg or "неожиданно" in msg or "意外" in msg

        # 4. Subsequent reconnect_failed event suppresses duplicate warning
        res_reconnect_fail = handler.handle_unexpected_disconnect(reason="reconnect_failed")
        assert res_reconnect_fail is False
        assert mock_notify.call_count == 1

    def test_connectivity_restored_silently_restores_tracking_for_subsequent_events(self, handler, mock_notify):
        """Verify connectivity_restored silently restores connection tracking after reconnect failure."""
        # 1. Connection established
        handler.handle_connected(profile_name="US-Fast")
        assert mock_notify.call_count == 1
        mock_notify.reset_mock()

        # 2. Connection drops and reconnect fails (reason="no_internet")
        handler.handle_connecting()
        handler.handle_connect_failed(reason="no_internet")
        assert mock_notify.call_count == 1
        mock_notify.reset_mock()

        # 3. Active monitor detects core self-healed and emits connectivity_restored event
        handler._on_connection_state_event({"event_name": "connectivity_restored", "data": {"profile_name": "US-Fast"}})

        # Must NOT send another notification (silent restoration)
        mock_notify.assert_not_called()
        assert handler._state == NotificationConnectionState.CONNECTED
        assert handler._was_connected is True

        # 4. Subsequent manual disconnect notifies properly
        res_dc = handler.handle_disconnected(is_manual=True)
        assert res_dc is True
        assert mock_notify.call_count == 1
        msg, _ = mock_notify.call_args[0]
        assert "Disconnected" in msg or "قطع شد" in msg or "Отключено" in msg or "已断开" in msg

    # -------------------------------------------------------------------------
    # 8. Application shutdown
    # -------------------------------------------------------------------------

    def test_application_shutdown_suppresses_notifications(self, handler, mock_notify):
        """Clean application shutdown suppresses disconnect notifications."""
        handler.handle_connected(profile_name="US-Fast")
        mock_notify.reset_mock()

        handler.set_shutting_down(True)
        res = handler.handle_disconnected(is_manual=True)

        assert res is False
        mock_notify.assert_not_called()

    def test_application_shutdown_suppresses_late_connected_notification(self, handler, mock_notify):
        """Late connected event during application shutdown is ignored and dispatches no notification."""
        handler.set_shutting_down(True)
        res = handler.handle_connected(profile_name="US-Fast")

        assert res is False
        mock_notify.assert_not_called()

    def test_application_shutdown_suppresses_late_connectivity_restored(self, handler, mock_notify):
        """Late connectivity_restored event during application shutdown is ignored."""
        handler.set_shutting_down(True)
        handler.handle_connectivity_restored(profile_name="US-Fast")

        assert handler._state != NotificationConnectionState.CONNECTED
        mock_notify.assert_not_called()

    # -------------------------------------------------------------------------
    # 9. Fail-soft behavior
    # -------------------------------------------------------------------------

    def test_fail_soft_when_os_notification_raises(self, test_bus):
        """A failure in OS notification dispatch must never crash or raise."""
        broken_notify = MagicMock(side_effect=RuntimeError("OS Notification Center unavailable"))
        h = ConnectionNotificationHandler(notify_fn=broken_notify, bus=test_bus)

        # Should NOT raise
        res = h.handle_connected(profile_name="Server")
        assert res is True
        assert h._state == NotificationConnectionState.CONNECTED

    # -------------------------------------------------------------------------
    # 10. Systray integration
    # -------------------------------------------------------------------------

    def test_systray_dispatch(self, mock_systray, test_bus):
        """Notification dispatches through systray.notify(message, title)."""
        h = ConnectionNotificationHandler(systray=mock_systray, bus=test_bus)
        h.handle_connected(profile_name="Proxy-1")

        mock_systray.notify.assert_called_once()
        msg, title = mock_systray.notify.call_args[0]
        assert "Proxy-1" in msg
        assert title == "XenRay"

    # -------------------------------------------------------------------------
    # 11. EventBus Pub/Sub Integration
    # -------------------------------------------------------------------------

    def test_event_bus_pub_sub_lifecycle(self, test_bus, mock_notify):
        """End-to-end event bus message routing drives notifications correctly."""
        h = ConnectionNotificationHandler(
            selected_profile_getter=lambda: {"name": "Frankfurt-01"},
            notify_fn=mock_notify,
            bus=test_bus,
        )
        h.start()

        # 1. Emit connected over EventBus
        test_bus.publish(
            TOPIC_CONNECTION_STATE_CHANGED,
            EngineEvent(
                event_name="connected",
                source="connection_manager",
                payload={"event": "connected", "data": {"profile_name": "Frankfurt-01"}},
            ),
        )
        assert mock_notify.call_count == 1
        assert "Frankfurt-01" in mock_notify.call_args[0][0]

        # 2. Emit duplicate connected event
        test_bus.publish(
            TOPIC_CONNECTION_STATE_CHANGED,
            EngineEvent(
                event_name="connected",
                source="connection_manager",
                payload={"event": "connected", "data": {}},
            ),
        )
        assert mock_notify.call_count == 1

        # 3. Emit core crashed
        test_bus.publish(EVENT_CORE_CRASHED, {"crashed_engine": "xray", "pid": 1234})
        assert mock_notify.call_count == 2
        assert "unexpectedly" in mock_notify.call_args[0][0]

        h.cleanup()

    def test_connectivity_lost_triggers_unexpected_disconnect_notification(self, test_bus, mock_notify):
        """connectivity_lost event from ConnectionManager routes to unexpected disconnect notification."""
        h = ConnectionNotificationHandler(
            selected_profile_getter=lambda: {"name": "Frankfurt-01"},
            notify_fn=mock_notify,
            bus=test_bus,
        )
        h.start()

        # Connect first
        test_bus.publish(
            TOPIC_CONNECTION_STATE_CHANGED,
            EngineEvent(
                event_name="connected",
                source="connection_manager",
                payload={"event": "connected", "data": {"profile_name": "Frankfurt-01"}},
            ),
        )
        assert mock_notify.call_count == 1
        mock_notify.reset_mock()

        # Emit connectivity_lost
        test_bus.publish(
            TOPIC_CONNECTION_STATE_CHANGED,
            EngineEvent(
                event_name="connectivity_lost",
                source="connection_manager",
                payload={"event": "connectivity_lost", "data": {"reason": "ping_timeout"}},
            ),
        )
        assert mock_notify.call_count == 1
        msg, title = mock_notify.call_args[0]
        assert "unexpectedly" in msg
        assert h._state == NotificationConnectionState.DISCONNECTED

        h.cleanup()
