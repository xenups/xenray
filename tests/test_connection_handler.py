"""Tests for ConnectionHandler post-connection verification."""

from unittest.mock import MagicMock, patch

from src.core.types import ConnectionMode
from src.ui.handlers.connection_handler import ConnectionHandler


class TestPostConnectionCheck:
    """Post-connection verification must match the active connection mode."""

    def _fake_network_utils(self):
        n = MagicMock()
        n.check_internet_connection.return_value = True
        n.check_proxy_connectivity.return_value = True
        return n

    def test_vpn_mode_uses_proxy_check(self):
        """VPN/TUN mode verifies through the SOCKS proxy (tunnel egress)."""
        n = self._fake_network_utils()
        ok = ConnectionHandler._post_connection_check(n, ConnectionMode.VPN, 10805)
        assert ok is True
        n.check_proxy_connectivity.assert_called_once_with(10805, timeout=3.0, retries=2)
        n.check_internet_connection.assert_not_called()

    def test_vpn_mode_without_proxy_port_fails(self):
        """VPN mode without a configured proxy port cannot be verified."""
        n = self._fake_network_utils()
        ok = ConnectionHandler._post_connection_check(n, ConnectionMode.VPN, 0)
        assert ok is False
        n.check_proxy_connectivity.assert_not_called()

    def test_proxy_mode_uses_direct_check(self):
        """Proxy mode keeps the direct internet check."""
        n = self._fake_network_utils()
        ok = ConnectionHandler._post_connection_check(n, ConnectionMode.PROXY, 10805)
        assert ok is True
        n.check_internet_connection.assert_called_once_with()
        n.check_proxy_connectivity.assert_not_called()


class TestVerifyPostConnection:
    """Post-connection re-check is advisory: it never tears down a connection."""

    def _handler(self):
        handler = ConnectionHandler(
            connection_manager=MagicMock(),
            app_context=MagicMock(),
            network_stats=MagicMock(),
        )
        handler._current_mode_getter = lambda: ConnectionMode.VPN
        handler._app_context.settings.get_proxy_port.return_value = 10805
        return handler

    @patch("time.sleep")
    @patch.object(ConnectionHandler, "_post_connection_check")
    def test_success_on_first_attempt(self, mock_check, mock_sleep):
        """A passing probe confirms the connection."""
        handler = self._handler()
        mock_check.return_value = True

        ok = handler._verify_post_connection()

        assert ok is True
        assert mock_check.call_count == 1
        handler._connection_manager.disconnect.assert_not_called()

    @patch("time.sleep")
    @patch.object(ConnectionHandler, "_post_connection_check")
    def test_transient_failure_then_success(self, mock_check, mock_sleep):
        """A transient failure followed by success does NOT tear down."""
        handler = self._handler()
        mock_check.side_effect = [False, True]

        ok = handler._verify_post_connection()

        assert ok is True
        assert mock_check.call_count == 2
        handler._connection_manager.disconnect.assert_not_called()

    @patch("time.sleep")
    @patch.object(ConnectionHandler, "_post_connection_check")
    def test_persistent_failure_keeps_connection(self, mock_check, mock_sleep):
        """Persistent probe failures do NOT tear down a verified-healthy connection."""
        handler = self._handler()
        mock_check.return_value = False

        ok = handler._verify_post_connection()

        assert ok is True
        assert mock_check.call_count == 2
        handler._connection_manager.disconnect.assert_not_called()
