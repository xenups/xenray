"""Tests: ping/latency probe routes through the SNI-spoof relay when enabled."""

from unittest.mock import patch

from src.services.connection.connection_tester import ConnectionTester


class TestSniSpoofEndpoint:
    def test_disabled_returns_none(self, monkeypatch):
        class _Repo:
            def get_sni_spoof_enabled(self):
                return False

        monkeypatch.setattr(
            "src.repositories.settings_repository.SettingsRepository",
            lambda *a, **k: _Repo(),
        )
        assert ConnectionTester._sni_spoof_endpoint() is None

    def test_enabled_returns_listener(self, monkeypatch):
        class _Repo:
            def get_sni_spoof_enabled(self):
                return True

            def get_sni_listen_host(self):
                return "127.0.0.1"

            def get_sni_listen_port(self):
                return 40443

        monkeypatch.setattr(
            "src.repositories.settings_repository.SettingsRepository",
            lambda *a, **k: _Repo(),
        )
        ep = ConnectionTester._sni_spoof_endpoint()
        assert ep == {"host": "127.0.0.1", "port": 40443}

    def test_bad_listener_returns_none(self, monkeypatch):
        class _Repo:
            def get_sni_spoof_enabled(self):
                return True

            def get_sni_listen_port(self):
                return 0  # invalid

        monkeypatch.setattr(
            "src.repositories.settings_repository.SettingsRepository",
            lambda *a, **k: _Repo(),
        )
        assert ConnectionTester._sni_spoof_endpoint() is None


class TestSniSpoofProbe:
    def test_probe_connect_success_measures_rtt(self, monkeypatch):
        """Successful connect to the relay returns (True, rtt_ms) and only
        measures the TCP handshake round-trip."""

        class _Sock:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        fake_sock = _Sock()

        with patch(
            "src.services.connection.connection_tester.socket.create_connection",
            return_value=fake_sock,
        ) as m_conn, patch(
            "src.services.connection.connection_tester.time.monotonic",
            side_effect=[100.0, 100.05],  # start, end -> 50ms
        ):
            ok, latency = ConnectionTester._sni_spoof_probe({"host": "127.0.0.1", "port": 40443})
        assert ok is True
        assert latency == 50
        # probed the relay, NOT a raw server IP
        m_conn.assert_called_once_with(("127.0.0.1", 40443), timeout=5)

    def test_probe_connect_failure_returns_not_ok(self, monkeypatch):
        with patch(
            "src.services.connection.connection_tester.socket.create_connection",
            side_effect=ConnectionRefusedError("refused"),
        ):
            ok, latency = ConnectionTester._sni_spoof_probe({"host": "127.0.0.1", "port": 40443})
        assert ok is False
        assert latency == 999999


class TestSniSpoofProxyRouting:
    def test_socks_mode_uses_spoof_relay_when_enabled(self, monkeypatch):
        """With SNI enabled + socks_port, test_connection_sync probes the spoof
        relay (not the generic SOCKS proxy)."""
        monkeypatch.setattr(
            ConnectionTester,
            "_sni_spoof_endpoint",
            lambda: {"host": "127.0.0.1", "port": 40443},
        )
        monkeypatch.setattr(
            ConnectionTester,
            "_sni_spoof_probe",
            lambda sni: (True, 42),
        )
        ok, result, country = ConnectionTester.test_connection_sync({}, fetch_country=False, socks_port=10805)
        assert ok is True
        # 42ms reported
        assert "42" in result

    def test_socks_mode_keeps_standard_when_disabled(self, monkeypatch):
        """With SNI disabled, the standard SOCKS proxy connectivity path is used."""
        monkeypatch.setattr(ConnectionTester, "_sni_spoof_endpoint", lambda: None)

        from src.utils import network_utils

        monkeypatch.setattr(
            network_utils.NetworkUtils,
            "check_proxy_connectivity",
            staticmethod(lambda port: True),
        )
        ok, result, country = ConnectionTester.test_connection_sync({}, fetch_country=False, socks_port=10805)
        assert ok is True


class TestSniSpoofDirectModeRouting:
    def test_direct_mode_uses_spoof_relay_when_enabled(self, monkeypatch):
        """With SNI enabled + socks_port=0 (Direct Xray mode), the probe still
        goes through the spoof relay, not a bare direct Xray spawn to a
        possibly-filtered server (the Server List ping path)."""
        monkeypatch.setattr(
            ConnectionTester,
            "_sni_spoof_endpoint",
            lambda: {"host": "127.0.0.1", "port": 40443},
        )
        monkeypatch.setattr(
            ConnectionTester,
            "_sni_spoof_probe",
            lambda sni: (True, 37),
        )
        # Direct mode (test_connection_sync currently lacks socks_port) must NOT
        # spawn an Xray nor probe generate_204 — it short-circuits via the relay.
        ok, result, country = ConnectionTester.test_connection_sync({}, fetch_country=False, socks_port=0)
        assert ok is True
        assert "37" in result

    def test_direct_mode_keeps_standard_when_disabled(self, monkeypatch):
        """With SNI disabled, Direct mode proceeds to the standard path (spawning
        Xray etc.) — i.e. it must NOT short-circuit via the relay."""
        monkeypatch.setattr(ConnectionTester, "_sni_spoof_endpoint", lambda: None)
        # Without SNI, Direct mode reaches the "no valid outbound" error path
        # (no Xray spawn) — proving the SNI gate was skipped.
        ok, result, country = ConnectionTester.test_connection_sync({}, fetch_country=False, socks_port=0)
        assert ok is False
        assert "invalid" in result.lower() or "config" in result.lower()


class TestSniSpoofRelayFallback:
    def test_relay_down_falls_back_to_socks(self, monkeypatch):
        """When SNI is enabled but the relay is NOT listening (listener not up
        yet / mid-reconnect), the probe must NOT report Connection Error — it
        falls through to the standard SOCKS path, which may still succeed."""
        monkeypatch.setattr(
            ConnectionTester,
            "_sni_spoof_endpoint",
            lambda: {"host": "127.0.0.1", "port": 40443},
        )
        # Relay connect fails (refused) → fall through below
        monkeypatch.setattr(ConnectionTester, "_sni_spoof_probe", lambda sni: (False, 999999))

        from src.utils import network_utils

        monkeypatch.setattr(
            network_utils.NetworkUtils,
            "check_proxy_connectivity",
            staticmethod(lambda port: True),
        )
        ok, result, country = ConnectionTester.test_connection_sync({}, fetch_country=False, socks_port=10805)
        # Even though relay was down, the SOCKS fallback succeeded → no error.
        assert ok is True

    def test_relay_down_and_socks_down_reports_error(self, monkeypatch):
        """Relay down AND SOCKS down → real Connection Error (both paths dead)."""
        monkeypatch.setattr(
            ConnectionTester,
            "_sni_spoof_endpoint",
            lambda: {"host": "127.0.0.1", "port": 40443},
        )
        monkeypatch.setattr(ConnectionTester, "_sni_spoof_probe", lambda sni: (False, 999999))

        from src.utils import network_utils

        monkeypatch.setattr(
            network_utils.NetworkUtils,
            "check_proxy_connectivity",
            staticmethod(lambda port: False),
        )
        ok, result, country = ConnectionTester.test_connection_sync({}, fetch_country=False, socks_port=10805)
        assert ok is False
