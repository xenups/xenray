"""Tests for ConnectionHandler post-connection verification."""

from unittest.mock import MagicMock

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
        n.check_proxy_connectivity.assert_called_once_with(10805)
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
