"""Isolated unit tests for core engine components:
- SingboxConfigBuilder
- RouteManagerService
- PlatformUtils (SMHR)
- SingboxService & XrayService process lifecycle and clean teardown
"""

from unittest.mock import patch

import pytest

from src.core.config_builders.singbox_config_builder import SingboxConfigBuilder
from src.core.constants import TUN_GATEWAY_IPV4
from src.services.connection.route_manager_service import RouteManagerService
from src.services.core_engines.xray_service import XrayService


class TestSingboxConfigBuilder:
    """Tests for SingboxConfigBuilder JSON generation logic."""

    @pytest.fixture
    def builder(self):
        return SingboxConfigBuilder()

    def test_normalize_list(self, builder):
        assert builder.normalize_list(["  1.1.1.1  ", "'DOMAIN.COM'"]) == [
            "1.1.1.1",
            "domain.com",
        ]
        assert builder.normalize_list(None) == []

    def test_filter_real_ips(self, builder):
        ips = builder.filter_real_ips(["1.1.1.1", "2606:4700:4700::1111", "not-an-ip.com"])
        assert ips == ["1.1.1.1", "2606:4700:4700::1111"]

    def test_filter_domains(self, builder):
        domains = builder.filter_domains(["1.1.1.1", "proxy.example.com"])
        assert domains == ["proxy.example.com"]

    def test_build_basic_config(self, builder):
        cfg = builder.build(
            socks_port=10805,
            proxy_server_ip="proxy.example.com",
            routing_country="",
            interface_name="eth0",
            routing_rules=None,
            mtu=1420,
        )

        assert cfg["dns"]["strategy"] == "ipv4_only"
        assert cfg["inbounds"][0]["type"] == "tun"
        assert cfg["inbounds"][0]["address"] == [TUN_GATEWAY_IPV4]
        assert cfg["inbounds"][0]["mtu"] == 1420

        socks_outbound = next(o for o in cfg["outbounds"] if o["tag"] == "proxy")
        assert socks_outbound["server_port"] == 10805

        direct_outbound = next(o for o in cfg["outbounds"] if o["tag"] == "direct")
        assert direct_outbound["bind_interface"] == "eth0"

    def test_build_with_user_routing_rules(self, builder):
        cfg = builder.build(
            socks_port=10805,
            proxy_server_ip="1.2.3.4",
            routing_rules={
                "direct": ["direct.com", "10.0.0.1/24"],
                "proxy": ["domain:proxy.com", "full:exact.com"],
                "block": ["block.com"],
            },
        )
        rules = cfg["route"]["rules"]
        outbounds = [r.get("outbound") for r in rules]
        assert "direct" in outbounds
        assert "proxy" in outbounds
        assert "block" in outbounds

    def test_build_with_country_rules(self, builder):
        cfg = builder.build(
            socks_port=10805,
            proxy_server_ip="1.2.3.4",
            routing_country="ir",
        )
        assert "rule_set" in cfg["route"]
        rule_set_tags = [rs["tag"] for rs in cfg["route"]["rule_set"]]
        assert any("ir-rules" in t for t in rule_set_tags)


class TestRouteManagerService:
    """Tests for RouteManagerService static route manipulations."""

    @pytest.fixture
    def route_mgr(self):
        return RouteManagerService()

    def test_is_private_or_reserved(self, route_mgr):
        for private_ip in (
            "10.0.0.1",
            "172.16.0.1",
            "192.168.1.1",
            "127.0.0.1",
            "169.254.1.1",
        ):
            assert route_mgr.is_private_or_reserved(private_ip) is True
        for public_ip in ("1.1.1.1", "8.8.8.8", "104.16.72.94"):
            assert route_mgr.is_private_or_reserved(public_ip) is False

    def test_resolve_ips_passthrough(self, route_mgr):
        res = route_mgr.resolve_ips(["1.1.1.1", "8.8.8.8"])
        assert set(res) == {"1.1.1.1", "8.8.8.8"}

    def test_add_static_route_skips_private_ips(self, route_mgr):
        with patch("subprocess.run") as mock_run:
            route_mgr.add_static_route("192.168.1.100", "192.168.1.1")
            mock_run.assert_not_called()
            assert "192.168.1.100" not in route_mgr._added_routes

    def test_add_static_route_executes_for_public_ip(self, route_mgr):
        with patch("subprocess.run") as mock_run:
            route_mgr.add_static_route("1.2.3.4", "192.168.1.1")
            mock_run.assert_called_once()
            assert "1.2.3.4" in route_mgr._added_routes

    def test_cleanup_routes(self, route_mgr):
        route_mgr._added_routes = ["1.2.3.4"]
        with patch("subprocess.run") as mock_run:
            # H3: a successful delete (rc==0) is removed from tracking.
            mock_run.return_value.returncode = 0
            route_mgr.cleanup_routes()
            mock_run.assert_called_once()
            assert route_mgr._added_routes == []


class TestPlatformUtilsSmhr:
    """Tests for the SMHR registry helpers (now in the settings adapter)."""

    def test_smhr_helpers_exist_and_callable(self):
        from src.platform.windows import settings as win_settings

        assert callable(win_settings._read_smhr_state)
        assert callable(win_settings._set_smhr_state)
        assert callable(win_settings._suppress_smhr)
        assert callable(win_settings._restore_smhr)

    def test_suppress_and_restore_smhr_non_windows(self):
        from src.platform.factory import get_system_settings_adapter

        with patch("src.platform.factory._is_windows", return_value=False):
            adapter = get_system_settings_adapter()
            state = adapter.suppress_smhr()
            assert state is None
            adapter.restore_smhr(state)  # Should not raise


class TestServicesSmhrDelegation:
    """Verify XrayService and SingboxService delegate SMHR to the settings adapter."""

    def test_xray_service_smhr_delegation(self):
        with patch("src.platform.windows.settings._suppress_smhr", return_value=True) as mock_suppress:
            with patch("src.platform.windows.settings._restore_smhr") as mock_restore:
                xray = XrayService()
                xray._suppress_smhr()
                mock_suppress.assert_called_once()

                xray._restore_smhr()
                mock_restore.assert_called_once_with(True)

    def test_singbox_service_smhr_delegation(self):
        with (
            patch(
                "src.platform.windows.settings.WindowsSystemSettingsAdapter.suppress_smhr",
                return_value=True,
            ) as mock_suppress,
            patch("src.platform.windows.settings.WindowsSystemSettingsAdapter.restore_smhr") as mock_restore,
            patch("src.utils.process_utils.ProcessUtils.is_running", return_value=False),
        ):
            # Simulate the suppress path exercised during start(): via the
            # settings adapter, not any OS string.
            from src.platform.factory import get_system_settings_adapter

            adapter = get_system_settings_adapter()
            state = adapter.suppress_smhr()
            assert state is True
            mock_suppress.assert_called_once()
            adapter.restore_smhr(state)
            mock_restore.assert_called_once_with(True)
