"""Unit tests for ConnectionFSM state machine and disconnection cleanup pipeline."""

import unittest
from unittest.mock import MagicMock

from src.core.connection_fsm import ConnectionFSM, ConnectionState
from src.ui.handlers.connection_handler import ConnectionHandler


class TestConnectionFSM(unittest.TestCase):
    """Test suite verifying FSM transition rules and race condition guards."""

    def setUp(self):
        self.fsm = ConnectionFSM()

    def test_initial_state_is_disconnected(self):
        self.assertEqual(self.fsm.state, ConnectionState.DISCONNECTED)

    def test_valid_lifecycle_transitions(self):
        # DISCONNECTED -> CONNECTING
        self.assertTrue(self.fsm.transition_to(ConnectionState.CONNECTING))
        self.assertEqual(self.fsm.state, ConnectionState.CONNECTING)

        # CONNECTING -> CONNECTED
        self.assertTrue(self.fsm.transition_to(ConnectionState.CONNECTED))
        self.assertEqual(self.fsm.state, ConnectionState.CONNECTED)

        # CONNECTED -> DISCONNECTING
        self.assertTrue(self.fsm.transition_to(ConnectionState.DISCONNECTING))
        self.assertEqual(self.fsm.state, ConnectionState.DISCONNECTING)

        # DISCONNECTING -> DISCONNECTED
        self.assertTrue(self.fsm.transition_to(ConnectionState.DISCONNECTED))
        self.assertEqual(self.fsm.state, ConnectionState.DISCONNECTED)

    def test_reject_duplicate_connecting_transition(self):
        self.assertTrue(self.fsm.transition_to(ConnectionState.CONNECTING))
        # Second CONNECTING transition must be ignored/rejected
        self.assertFalse(self.fsm.transition_to(ConnectionState.CONNECTING))
        self.assertEqual(self.fsm.state, ConnectionState.CONNECTING)

    def test_reject_connecting_while_disconnecting(self):
        self.fsm.transition_to(ConnectionState.CONNECTING)
        self.fsm.transition_to(ConnectionState.CONNECTED)
        self.fsm.transition_to(ConnectionState.DISCONNECTING)

        # Attempt to connect while in DISCONNECTING must be rejected
        self.assertFalse(self.fsm.transition_to(ConnectionState.CONNECTING))
        self.assertEqual(self.fsm.state, ConnectionState.DISCONNECTING)

    def test_abrupt_disconnect_during_connecting(self):
        self.fsm.transition_to(ConnectionState.CONNECTING)
        # Abrupt disconnect during connecting must be allowed
        self.assertTrue(self.fsm.transition_to(ConnectionState.DISCONNECTING))
        self.assertEqual(self.fsm.state, ConnectionState.DISCONNECTING)

    def test_force_terminal_disconnected_state(self):
        self.fsm.transition_to(ConnectionState.CONNECTING)
        self.fsm.force_state(ConnectionState.DISCONNECTED)
        self.assertEqual(self.fsm.state, ConnectionState.DISCONNECTED)


class TestConnectionHandlerFSMIntegration(unittest.TestCase):
    """Test suite verifying ConnectionHandler integration with FSM guards and cleanup pipeline."""

    def setUp(self):
        self.mock_manager = MagicMock()
        self.mock_app_context = MagicMock()
        self.mock_stats = MagicMock()
        self.handler = ConnectionHandler(self.mock_manager, self.mock_app_context, self.mock_stats)

        self.handler.setup(
            ui_helper=None,
            connection_button=MagicMock(),
            status_display=MagicMock(),
            log_viewer=MagicMock(),
            toast=MagicMock(),
            systray=MagicMock(),
            logs_drawer_component=MagicMock(),
            latency_monitor_handler=MagicMock(),
            is_running_getter=lambda: self.handler.fsm.is_state(ConnectionState.CONNECTED),
            is_running_setter=MagicMock(),
            connecting_getter=lambda: self.handler.fsm.is_state(ConnectionState.CONNECTING),
            connecting_setter=MagicMock(),
            selected_profile_getter=lambda: {'id': 'p1', 'name': 'Test'},
            current_mode_getter=lambda: 'vpn',
            update_horizon_glow_callback=MagicMock(),
            profile_manager_is_running_setter=MagicMock(),
            monitoring_service_is_running_setter=MagicMock(),
        )

    def test_handler_connect_async_fsm_guard(self):
        # Transition state to CONNECTING via FSM
        self.handler.fsm.transition_to(ConnectionState.CONNECTING)

        # Call connect_async again — must be hard rejected at top of method
        self.handler.connect_async()
        self.assertEqual(self.handler.fsm.state, ConnectionState.CONNECTING)

    def test_handler_disconnect_fsm_guard(self):
        # Set state to DISCONNECTED
        self.handler.fsm.force_state(ConnectionState.DISCONNECTED)

        # Call disconnect when already DISCONNECTED — must be hard rejected at top
        self.handler.disconnect()
        self.assertEqual(self.handler.fsm.state, ConnectionState.DISCONNECTED)

    def test_handler_reset_ui_forces_disconnected_state(self):
        self.handler.fsm.transition_to(ConnectionState.CONNECTING)
        self.handler.reset_ui_disconnected()
        self.assertEqual(self.handler.fsm.state, ConnectionState.DISCONNECTED)

    def test_perform_connect_task_exception_triggers_cleanup(self):
        # Mock _check_internet to raise an exception deep in task execution
        self.handler._check_internet = MagicMock(side_effect=RuntimeError("Process spawn error"))
        self.handler.fsm.transition_to(ConnectionState.CONNECTING)

        # Execute task logic
        self.handler._perform_connect_task()

        # State must cleanly settle back to DISCONNECTED via try/finally
        self.assertEqual(self.handler.fsm.state, ConnectionState.DISCONNECTED)


if __name__ == '__main__':
    unittest.main()
