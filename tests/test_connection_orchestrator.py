from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.core.connection_orchestrator import ConnectionOrchestrator


class TestConnectionOrchestrator:
    @pytest.fixture
    def orchestrator(self):
        # Mock all dependencies
        self.mock_config_mgr = MagicMock()
        self.mock_config_proc = MagicMock()
        self.mock_net_val = MagicMock()
        self.mock_xray_proc = MagicMock()
        self.mock_routing_mgr = MagicMock()
        self.mock_xray_svc = MagicMock()
        self.mock_singbox_svc = MagicMock()
        self.mock_obs = MagicMock()
        self.mock_log_mon = MagicMock()

        return ConnectionOrchestrator(
            self.mock_config_mgr,
            self.mock_config_proc,
            self.mock_net_val,
            self.mock_xray_proc,
            self.mock_routing_mgr,
            self.mock_xray_svc,
            self.mock_singbox_svc,
            self.mock_obs,
            self.mock_log_mon,
        )

    @patch("builtins.open", new_callable=mock_open)
    def test_establish_proxy_connection_success(self, mock_file, orchestrator):
        """Test successful proxy connection."""
        # Setup mocks
        orchestrator._config_manager.load_config.return_value = (
            {"outbounds": []},
            None,
        )
        orchestrator._network_validator.check_internet_connection.return_value = True
        orchestrator._xray_processor.process_config.return_value = {"processed": True}
        orchestrator._xray_processor.get_socks_port.return_value = 1080
        orchestrator._xray_service.start.return_value = 1234

        success, info = orchestrator.establish_connection("config.json", mode="proxy")

        assert success is True
        assert info["mode"] == "proxy"
        assert info["xray_pid"] == 1234
        assert info.get("singbox_pid") is None

        # Verify calls
        orchestrator._xray_service.start.assert_called_once()
        orchestrator._singbox_service.start.assert_not_called()

    @patch("builtins.open", new_callable=mock_open)
    def test_establish_vpn_connection_success(self, mock_file, orchestrator):
        """Test successful VPN connection."""
        # Setup mocks
        orchestrator._config_manager.load_config.return_value = (
            {"outbounds": []},
            None,
        )
        orchestrator._network_validator.check_internet_connection.return_value = True
        orchestrator._xray_processor.process_config.return_value = {"processed": True}
        orchestrator._xray_processor.get_socks_port.return_value = 1080
        orchestrator._xray_service.start.return_value = 1234
        orchestrator._singbox_service.start.return_value = 5678

        with patch("src.utils.network_utils.NetworkUtils.detect_optimal_mtu", return_value=1420):
            success, info = orchestrator.establish_connection("config.json", mode="vpn")

        assert success is True
        assert info["mode"] == "vpn"
        assert info["xray_pid"] == 1234
        assert info["singbox_pid"] == 5678

        # Verify calls
        orchestrator._xray_service.start.assert_called_once()
        orchestrator._singbox_service.start.assert_called_once()

    def test_teardown_connection(self, orchestrator):
        """Test connection teardown."""
        info = {"mode": "vpn", "xray_pid": 1234, "singbox_pid": 5678}

        orchestrator.teardown_connection(info)

        orchestrator._singbox_service.stop.assert_called_once()
        orchestrator._xray_service.stop.assert_called_once()

    @patch("builtins.open", new_callable=mock_open)
    def test_establish_connection_fail_xray(self, mock_file, orchestrator):
        """Test failure when Xray fails to start."""
        orchestrator._config_manager.load_config.return_value = (
            {"outbounds": []},
            None,
        )
        orchestrator._network_validator.check_internet_connection.return_value = True
        orchestrator._xray_processor.process_config.return_value = {"processed": True}
        orchestrator._xray_service.start.return_value = None  # Fail

        success, info = orchestrator.establish_connection("config.json", mode="proxy")

        assert success is False
        assert info is None
