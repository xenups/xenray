"""Tests: ping/latency probe routes through the SNI-spoof relay when enabled."""

from unittest.mock import MagicMock, patch

from src.services.connection.connection_tester import ConnectionTester


class TestSniSpoofEndpoint:
    def test_is_sni_spoof_enabled_false(self, monkeypatch):
        class _Repo:
            def get_sni_spoof_enabled(self):
                return False

        monkeypatch.setattr(
            "src.repositories.settings_repository.SettingsRepository",
            lambda *a, **k: _Repo(),
        )
        assert ConnectionTester._is_sni_spoof_enabled() is False
        assert ConnectionTester._sni_spoof_endpoint() is None

    def test_is_sni_spoof_enabled_true(self, monkeypatch):
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
        assert ConnectionTester._is_sni_spoof_enabled() is True
        assert ConnectionTester._sni_spoof_endpoint() == {
            "host": "127.0.0.1",
            "port": 40443,
        }

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
    def test_probe_measures_real_ttfb_through_relay(self, monkeypatch):
        """The probe sends a payload through the relay and waits for the FIRST
        byte back from the real server (TTFB) — not just an instant loopback
        connect."""

        class _Sock:
            def __init__(self):
                self.closed = False
                self.sent = b""

            def settimeout(self, t):
                pass

            def sendall(self, payload):
                self.sent = payload

            def recv(self, n):
                # first byte from the far server (e.g. a TLS alert) arrived
                return b"\x15"

            def close(self):
                self.closed = True

        fake_sock = _Sock()

        with (
            patch(
                "src.services.connection.connection_tester.socket.create_connection",
                return_value=fake_sock,
            ) as m_conn,
            patch(
                "src.services.connection.connection_tester.time.monotonic",
                side_effect=[100.0, 100.05],  # start, end -> 50ms
            ),
        ):
            ok, latency = ConnectionTester._sni_spoof_probe({"host": "127.0.0.1", "port": 40443})
        assert ok is True
        assert latency == 50
        assert fake_sock.sent  # a probe was actually forwarded
        # probed the relay, NOT a raw server IP
        m_conn.assert_called_once_with(("127.0.0.1", 40443), timeout=5)

    def test_probe_rejects_loopback_only_sub5ms(self, monkeypatch):
        """A reading < the real-internet floor (loopback-only, fake 0/1ms) is
        rejected instead of being reported as a valid ping."""

        class _Sock:
            def settimeout(self, t):
                pass

            def sendall(self, payload):
                pass

            def recv(self, n):
                return b"\x15"

            def close(self):
                pass

        with (
            patch(
                "src.services.connection.connection_tester.socket.create_connection",
                return_value=_Sock(),
            ),
            patch(
                "src.services.connection.connection_tester.time.monotonic",
                side_effect=[100.0, 100.001],  # delta = 1ms -> loopback fake
            ),
        ):
            ok, latency = ConnectionTester._sni_spoof_probe({"host": "127.0.0.1", "port": 40443})
        assert ok is False
        assert latency == 999999

    def test_probe_connect_failure_returns_not_ok(self, monkeypatch):
        with patch(
            "src.services.connection.connection_tester.socket.create_connection",
            side_effect=ConnectionRefusedError("refused"),
        ):
            ok, latency = ConnectionTester._sni_spoof_probe({"host": "127.0.0.1", "port": 40443})
        assert ok is False
        assert latency == 999999


class TestSniSpoofDisabledShortCircuit:
    def test_disabled_never_invokes_relay_probe(self, monkeypatch):
        """When SNI Spoof is disabled, the standard probe runs immediately and the
        relay probe (and its timeout/fallback logs) is NEVER touched."""
        monkeypatch.setattr(ConnectionTester, "_is_sni_spoof_enabled", staticmethod(lambda: False))
        monkeypatch.setattr(
            ConnectionTester,
            "_sni_spoof_probe",
            staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("relay probed while disabled"))),
        )
        from src.utils import network_utils

        monkeypatch.setattr(
            network_utils.NetworkUtils,
            "check_proxy_connectivity",
            staticmethod(lambda port: True),
        )
        ok, result, _ = ConnectionTester.test_connection_sync({}, fetch_country=False, socks_port=10805)
        assert ok is True  # standard SOCKS path, no relay probe/fallback


class TestSniSpoofProxyRouting:
    def test_socks_mode_uses_spoof_relay_when_enabled(self, monkeypatch):
        """With SNI enabled + socks_port, test_connection_sync probes the spoof
        relay (not the generic SOCKS proxy)."""
        monkeypatch.setattr(
            ConnectionTester,
            "_is_sni_spoof_enabled",
            lambda: True,
        )
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
        """With SNI disabled, the standard SOCKS proxy connectivity path is used
        and relay probe is never called."""
        monkeypatch.setattr(ConnectionTester, "_is_sni_spoof_enabled", lambda: False)
        probe_mock = MagicMock()
        monkeypatch.setattr(ConnectionTester, "_sni_spoof_probe", probe_mock)

        from src.utils import network_utils

        monkeypatch.setattr(
            network_utils.NetworkUtils,
            "check_proxy_connectivity",
            staticmethod(lambda port: True),
        )
        ok, result, country = ConnectionTester.test_connection_sync({}, fetch_country=False, socks_port=10805)
        assert ok is True
        probe_mock.assert_not_called()


class TestSniSpoofDirectModeRouting:
    def test_direct_mode_uses_spoof_relay_when_enabled(self, monkeypatch):
        """With SNI enabled + socks_port=0 (Direct Xray mode), the probe still
        goes through the spoof relay, not a bare direct Xray spawn to a
        possibly-filtered server (the Server List ping path)."""
        monkeypatch.setattr(
            ConnectionTester,
            "_is_sni_spoof_enabled",
            lambda: True,
        )
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
        """With SNI disabled, Direct mode proceeds directly to the standard path
        (spawning Xray etc.) and never calls the relay probe."""
        monkeypatch.setattr(ConnectionTester, "_is_sni_spoof_enabled", lambda: False)
        probe_mock = MagicMock()
        monkeypatch.setattr(ConnectionTester, "_sni_spoof_probe", probe_mock)

        # Without SNI, Direct mode reaches the "no valid outbound" error path
        # (no Xray spawn) — proving the SNI gate was skipped.
        ok, result, country = ConnectionTester.test_connection_sync({}, fetch_country=False, socks_port=0)
        assert ok is False
        assert "invalid" in result.lower() or "config" in result.lower()
        probe_mock.assert_not_called()


class TestSniSpoofRelayFallback:
    def test_relay_down_falls_back_to_socks(self, monkeypatch):
        """When SNI is enabled but the relay is NOT listening (listener not up
        yet / mid-reconnect), the probe must NOT report Connection Error — it
        falls through to the standard SOCKS path, which may still succeed."""
        monkeypatch.setattr(
            ConnectionTester,
            "_is_sni_spoof_enabled",
            lambda: True,
        )
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
            "_is_sni_spoof_enabled",
            lambda: True,
        )
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
