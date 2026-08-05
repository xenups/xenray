from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.core.connection_orchestrator import ConnectionOrchestrator


class TestConnectionOrchestrator:
    @pytest.fixture
    def orchestrator(self):
        # Mock all dependencies
        self.mock_app_context = MagicMock()
        self.mock_net_val = MagicMock()
        self.mock_xray_proc = MagicMock()
        self.mock_xray_svc = MagicMock()
        self.mock_legacy_config_svc = MagicMock()

        # Configure legacy config service mock to return non-legacy by default
        self.mock_legacy_config_svc.is_legacy.return_value = False

        return ConnectionOrchestrator(
            self.mock_app_context,
            self.mock_net_val,
            self.mock_xray_proc,
            self.mock_xray_svc,
            self.mock_legacy_config_svc,
        )

    @patch("src.services.connection_tester.ConnectionTester.test_connection_sync")
    @patch("builtins.open", new_callable=mock_open)
    def test_establish_proxy_connection_success(self, mock_file, mock_conn_test, orchestrator):
        """Test successful proxy connection."""
        # Setup mocks
        orchestrator._app_context.load_config.return_value = (
            {"outbounds": []},
            None,
        )
        orchestrator._network_validator.check_internet_connection.return_value = True
        orchestrator._xray_processor.process_config.return_value = {"processed": True}
        orchestrator._xray_processor.get_socks_port.return_value = 1080
        orchestrator._xray_service.start.return_value = 1234
        mock_conn_test.return_value = (True, "50ms", None)  # Health check passes

        success, info = orchestrator.establish_connection("config.json", mode="proxy")

        assert success is True
        assert info["mode"] == "proxy"
        assert info["xray_pid"] == 1234

        # Verify calls
        orchestrator._xray_service.start.assert_called_once()

    @patch("src.services.connection_tester.ConnectionTester.test_connection_sync")
    @patch("builtins.open", new_callable=mock_open)
    def test_establish_vpn_connection_success(self, mock_file, mock_conn_test, orchestrator):
        """Test successful VPN connection."""
        # Setup mocks
        orchestrator._app_context.load_config.return_value = (
            {"outbounds": []},
            None,
        )
        orchestrator._network_validator.check_internet_connection.return_value = True
        orchestrator._xray_processor.process_config.return_value = {"processed": True}
        orchestrator._xray_processor.get_socks_port.return_value = 1080
        orchestrator._xray_service.start.return_value = 1234
        mock_conn_test.return_value = (True, "50ms", None)  # Health check passes

        with patch("src.utils.network_utils.NetworkUtils.detect_optimal_mtu", return_value=1420):
            success, info = orchestrator.establish_connection("config.json", mode="vpn")

        assert success is True
        assert info["mode"] == "vpn"
        assert info["xray_pid"] == 1234

        # Verify calls
        orchestrator._xray_service.start.assert_called_once()

    def test_teardown_connection(self, orchestrator):
        """Test connection teardown."""
        info = {"mode": "vpn", "xray_pid": 1234}

        orchestrator.teardown_connection(info)

        orchestrator._xray_service.stop.assert_called_once()

    @patch("builtins.open", new_callable=mock_open)
    def test_establish_connection_fail_xray(self, mock_file, orchestrator):
        """Test failure when Xray fails to start."""
        orchestrator._app_context.load_config.return_value = (
            {"outbounds": []},
            None,
        )
        orchestrator._network_validator.check_internet_connection.return_value = True
        orchestrator._xray_processor.process_config.return_value = {"processed": True}
        orchestrator._xray_service.start.return_value = None  # Fail

        success, info = orchestrator.establish_connection("config.json", mode="proxy")

        assert success is False
        assert info is None


class TestConnectionOrchestratorEngineSwitch:
    """Tests for XrayService / SingBoxService engine switching."""

    @pytest.fixture
    def dual_engine_orchestrator(self):
        mocks = {
            "app_context": MagicMock(),
            "net_val": MagicMock(),
            "xray_proc": MagicMock(),
            "xray_svc": MagicMock(),
            "legacy": MagicMock(),
            "singbox_svc": MagicMock(),
        }
        mocks["legacy"].is_legacy.return_value = False
        mocks["app_context"].load_config.return_value = ({"outbounds": []}, None)
        mocks["net_val"].check_internet_connection.return_value = True
        mocks["xray_proc"].process_config.return_value = {"processed": True}
        mocks["xray_proc"].get_socks_port.return_value = 1080
        mocks["xray_svc"].start.return_value = 1234
        mocks["singbox_svc"].start.return_value = 5678

        orch = ConnectionOrchestrator(
            mocks["app_context"],
            mocks["net_val"],
            mocks["xray_proc"],
            mocks["xray_svc"],
            mocks["legacy"],
            singbox_service=mocks["singbox_svc"],
        )
        return orch, mocks

    @patch("src.services.connection_tester.ConnectionTester.test_connection_sync")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.utils.network_utils.NetworkUtils.detect_optimal_mtu", return_value=1420)
    def test_vpn_uses_singbox_engine(self, mock_mtu, mock_file, mock_conn_test, dual_engine_orchestrator):
        """Selecting the sing-box TUN engine starts both Xray and sing-box."""
        orch, mocks = dual_engine_orchestrator
        mocks["app_context"].settings.get_tun_engine.return_value = "singbox"
        mock_conn_test.return_value = (True, "50ms", None)

        success, info = orch.establish_connection("config.json", mode="vpn")

        assert success is True
        assert info["xray_pid"] == 1234
        assert info["singbox_pid"] == 5678
        mocks["xray_svc"].start.assert_called_once()
        mocks["singbox_svc"].start.assert_called_once()
        # Xray config is processed as a proxy (no native TUN injection)
        mocks["xray_proc"].process_config.assert_called_once_with({"outbounds": []}, mode="proxy")

    @patch("src.services.connection_tester.ConnectionTester.test_connection_sync")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.utils.network_utils.NetworkUtils.detect_optimal_mtu", return_value=1420)
    def test_vpn_uses_xray_engine_by_default(self, mock_mtu, mock_file, mock_conn_test, dual_engine_orchestrator):
        """Default Xray TUN engine does not start sing-box."""
        orch, mocks = dual_engine_orchestrator
        mocks["app_context"].settings.get_tun_engine.return_value = "xray"
        mock_conn_test.return_value = (True, "50ms", None)

        success, info = orch.establish_connection("config.json", mode="vpn")

        assert success is True
        assert info["singbox_pid"] is None
        mocks["xray_svc"].start.assert_called_once()
        mocks["singbox_svc"].start.assert_not_called()

    @patch("src.services.connection_tester.ConnectionTester.test_connection_sync")
    @patch("builtins.open", new_callable=mock_open)
    @patch("src.utils.network_utils.NetworkUtils.detect_optimal_mtu", return_value=1420)
    def test_singbox_failure_stops_xray(self, mock_mtu, mock_file, mock_conn_test, dual_engine_orchestrator):
        """If sing-box fails to start, Xray is stopped and the attempt fails."""
        orch, mocks = dual_engine_orchestrator
        mocks["app_context"].settings.get_tun_engine.return_value = "singbox"
        mocks["singbox_svc"].start.return_value = None  # sing-box fails

        success, info = orch.establish_connection("config.json", mode="vpn")

        assert success is False
        mocks["xray_svc"].stop.assert_called_once()

    def test_teardown_stops_singbox_then_xray(self, dual_engine_orchestrator):
        """Teardown stops the sing-box TUN engine and the Xray proxy."""
        orch, mocks = dual_engine_orchestrator

        orch.teardown_connection({"xray_pid": 1234, "singbox_pid": 5678})

        mocks["singbox_svc"].stop.assert_called_once()
        mocks["xray_svc"].stop.assert_called_once()
