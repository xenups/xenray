import subprocess
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.services.singbox_service import SingboxService
from src.services.xray_service import XrayService


class TestXrayService:
    @pytest.fixture
    def xray_service(self):
        with patch("src.utils.process_utils.ProcessUtils.is_running", return_value=False):
            return XrayService()

    @patch("src.utils.process_utils.ProcessUtils.run_command")
    @patch("os.path.isfile", return_value=True)
    @patch("builtins.open", new_callable=mock_open)
    def test_start_success(self, mock_file, mock_isfile, mock_run, xray_service):
        """Test starting Xray successfully."""
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_run.return_value = mock_proc

        pid = xray_service.start("config.json")

        assert pid == 1234
        assert xray_service.pid == 1234
        mock_run.assert_called_once()
        # Verify PID file was written
        mock_file().write.assert_called_with("1234")

    @patch("src.utils.process_utils.ProcessUtils.kill_process")
    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data="1234"))
    def test_stop_success(self, mock_exists, mock_kill, xray_service):
        """Test stopping Xray."""
        xray_service._pid = 1234
        mock_kill.return_value = True

        with patch("os.remove") as mock_remove:
            assert xray_service.stop() is True
            assert xray_service.pid is None
            mock_kill.assert_called_with(1234, force=False)
            mock_remove.assert_called()


class TestSingboxService:
    @pytest.fixture
    def singbox_service(self):
        with patch("src.utils.process_utils.ProcessUtils.is_running", return_value=False):
            return SingboxService()

    @patch("src.utils.network_interface.NetworkInterfaceDetector.get_primary_interface")
    @patch("src.services.singbox_service.socket.create_connection")
    @patch("src.services.singbox_service.SingboxService._add_static_route")
    @patch("src.services.singbox_service.SingboxService._resolve_ips")
    @patch("src.services.singbox_service.SingboxService._write_config_and_start")
    def test_start_success(
        self,
        mock_write,
        mock_resolve,
        mock_add_route,
        mock_socket,
        mock_iface,
        singbox_service,
    ):
        """Test starting Sing-box successfully."""
        # Mock interface detection
        mock_iface.return_value = (
            "eth0",
            "192.168.1.5",
            "255.255.255.0",
            "192.168.1.1",
        )

        # Mock Xray ready check (socket connection succeeds)
        mock_socket.return_value.__enter__.return_value = MagicMock()

        # Mocking resolve_ips to return some IPs
        mock_resolve.return_value = ["1.1.1.1", "8.8.8.8"]

        # Mock write_config_and_start to succeed and set PID
        def fake_write(config):
            singbox_service._process = MagicMock()
            singbox_service._process.pid = 5678
            return True

        mock_write.side_effect = fake_write

        pid = singbox_service.start(xray_socks_port=1080)

        assert pid == 5678
        assert singbox_service.pid == 5678
        mock_write.assert_called_once()
        mock_add_route.assert_called()

    @patch("src.utils.process_utils.ProcessUtils.kill_process")
    def test_stop_with_routes_cleanup(self, mock_kill, singbox_service):
        """Test stopping Sing-box and cleaning up routes."""
        singbox_service._pid = 5678
        singbox_service._added_routes = ["1.1.1.1"]
        mock_kill.return_value = True

        with patch("subprocess.run") as mock_run, patch(
            "src.utils.platform_utils.PlatformUtils.get_platform", return_value="linux"
        ):
            singbox_service.stop()

            # Should have called ip route del
            mock_run.assert_called()
            assert singbox_service._added_routes == []

    def test_normalize_list(self, singbox_service):
        """Test list normalization helper."""
        inp = [" 1.1.1.1 ", " 'google.com' ", "[1.0.0.1]"]
        out = singbox_service._normalize_list(inp)
        assert out == ["1.1.1.1", "google.com", "1.0.0.1"]

    def test_generate_config_complex(self, singbox_service):
        """Test _generate_config with complex rules and bypasses."""
        routing_rules = {
            "direct": ["direct.com", "full:exact.com"],
            "proxy": ["proxy.com", "1.1.1.1/32"],
            "block": ["block.com", "geoip:ir", "geosite:category-ads-all"],
        }
        # Injects default toggles for coverage
        with patch(
            "src.core.config_manager.ConfigManager.get_routing_toggles",
            return_value={
                "block_udp_443": True,
                "block_ads": True,
                "direct_private_ips": True,
                "direct_local_domains": True,
            },
        ):
            # Signature: (self, socks_port, proxy_server_ip, routing_country="",
            #            interface_name=None, routing_rules=None, mtu=1420)
            config = singbox_service._generate_config(10805, "1.2.3.4", "ir", "eth0", routing_rules, 1500)

            # Check for block rule (it should be a suffix since no prefix)
            assert any(r.get("domain_suffix") == ["block.com"] for r in config["route"]["rules"])
            # Check for exact domain (full: prefix)
            assert any(r.get("domain") == ["exact.com"] for r in config["route"]["rules"])
            # Check for IP CIDR
            assert any(r.get("ip_cidr") == ["1.1.1.1/32"] for r in config["route"]["rules"])
            # Check for country rule (ir)
            assert any("ir" in str(r.get("rule_set")) for r in config["route"]["rules"] if "rule_set" in r)
            assert config["inbounds"][0]["mtu"] == 1500

    @patch("src.services.singbox_service.socket.getaddrinfo")
    def test_resolve_ips(self, mock_getaddr, singbox_service):
        """Test resolving IPs for bypass list."""
        mock_getaddr.side_effect = [
            [(None, None, None, None, ("1.1.1.1", 0))],
            [(None, None, None, None, ("2.2.2.2", 0))],
            OSError("Failed"),
        ]
        ips = singbox_service._resolve_ips(["one.com", "two.com", "fail.com"])
        assert "1.1.1.1" in ips
        assert "2.2.2.2" in ips
        assert len(ips) == 2

    def test_add_static_route_platforms(self, singbox_service):
        """Test route addition commands across platforms."""
        with patch("subprocess.run") as mock_run:
            # Linux
            with patch(
                "src.utils.platform_utils.PlatformUtils.get_platform",
                return_value="linux",
            ):
                # Signature: (self, ip, gateway)
                singbox_service._add_static_route("1.1.1.1", "192.168.1.1")
                mock_run.assert_called()

            # Windows
            with patch(
                "src.utils.platform_utils.PlatformUtils.get_platform",
                return_value="windows",
            ):
                singbox_service._add_static_route("2.2.2.2", "192.168.1.1")
                mock_run.assert_called()

    @patch("src.services.singbox_service.socket.create_connection")
    @patch("time.sleep", return_value=None)
    def test_wait_for_xray_ready_timeout(self, mock_sleep, mock_socket, singbox_service):
        """Test timeout when waiting for Xray."""
        mock_socket.side_effect = ConnectionRefusedError()
        assert singbox_service._wait_for_xray_ready(10805) is False
        assert mock_socket.call_count > 5  # Multiple retries

    @patch("src.utils.process_utils.ProcessUtils.run_command")
    @patch("src.services.singbox_service.ProcessUtils.run_command")
    @patch("builtins.open", new_callable=mock_open)
    def test_write_config_and_start(self, mock_file, mock_run_local, mock_run_utils, singbox_service):
        """Test writing JSON config and starting process."""
        mock_proc = MagicMock()
        mock_proc.pid = 999
        mock_run_local.return_value = mock_proc
        mock_run_utils.return_value = mock_proc

        config = {"test": True}
        # Ensure we are not using a real Popen
        with patch("subprocess.Popen") as mock_popen_call:
            mock_popen_call.return_value = mock_proc
            assert singbox_service._write_config_and_start(config) is True
            mock_file().write.assert_called()
            # We set self._process in _write_config_and_start
            assert singbox_service._process.pid == 999

    @patch("subprocess.run")
    def test_get_version(self, mock_run, singbox_service):
        """Test version discovery."""
        mock_proc = MagicMock()
        mock_proc.stdout = "sing-box version 1.12.12"
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        # Need to patch the executable path check
        with patch("os.path.exists", return_value=True):
            assert singbox_service.get_version() == "1.12.12"

        mock_run.side_effect = Exception("error")
        with patch("os.path.exists", return_value=True):
            assert singbox_service.get_version() is None

    def test_close_log(self, singbox_service):
        """Test log handle cleanup."""
        mock_handle = MagicMock()
        singbox_service._log_handle = mock_handle
        singbox_service._close_log()
        mock_handle.close.assert_called_once()
        assert singbox_service._log_handle is None

    def test_cleanup_routes_exception(self, singbox_service):
        """Test that cleanup doesn't crash on subprocess error."""
        singbox_service._added_routes = ["1.1.1.1"]
        # The implementation catches OSError and SubprocessError, not generic Exception
        with patch("subprocess.run", side_effect=subprocess.SubprocessError("oops")):
            singbox_service._cleanup_routes()
            # Should still clear the list via finally block
            assert singbox_service._added_routes == []

    def test_is_running_adoption(self, singbox_service):
        """Test is_running with adopted PID."""
        with patch("src.utils.process_utils.ProcessUtils.is_running", return_value=True):
            singbox_service._pid = 555
            assert singbox_service.is_running() is True

        with patch("src.utils.process_utils.ProcessUtils.is_running", return_value=False):
            assert singbox_service.is_running() is False
            assert singbox_service.pid is None  # Should be cleared now

    def test_generate_config_proxy_domain(self, singbox_service):
        """Test bypass rules for proxy domain."""
        config = singbox_service._generate_config(10805, "myproxy.com", "none")  # Proxy as domain
        # Should have rules for the domain
        assert any(r.get("domain_suffix") == "myproxy.com" for r in config["route"]["rules"])
        assert any(r.get("domain_suffix") == "myproxy.com" for r in config["dns"]["rules"])
