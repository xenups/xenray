"""Tests for SingboxService."""

from unittest.mock import MagicMock, patch

import pytest

from src.core.constants import TUN_GATEWAY_IPV4
from src.services.core_engines.singbox_service import SingboxService


@pytest.fixture
def service():
    with patch("src.utils.process_utils.ProcessUtils.is_running", return_value=True):
        return SingboxService()


class TestSingboxServiceInterface:
    """Interface contract tests for SingboxService."""

    def test_pid_is_property(self, service):
        assert isinstance(SingboxService.__dict__.get("pid"), property)

    def test_is_running_is_method(self):
        """is_running() is a method (matches the 0.1.17-beta contract)."""
        assert callable(SingboxService.is_running)

    def test_stop_is_idempotent(self, service):
        """stop() on an unstarted service must not raise."""
        service.stop()
        service.stop()


class TestConfigGeneration:
    """Tests for SingboxService._generate_config()."""

    def _config(self, service, **kwargs):
        defaults = {
            "socks_port": 10805,
            "proxy_server_ip": "",
            "routing_country": "",
            "interface_name": None,
            "routing_rules": None,
            "mtu": 1420,
        }
        defaults.update(kwargs)
        return service._generate_config(**defaults)

    def test_ipv4_only_tun_address(self, service):
        """TUN inbound carries a single IPv4 subnet (IPv6 disabled)."""
        cfg = self._config(service)
        tun = cfg["inbounds"][0]
        assert tun["type"] == "tun"
        assert tun["address"] == [TUN_GATEWAY_IPV4]
        assert not any(":" in a for a in tun["address"]), "No IPv6 addresses allowed"
        assert tun["auto_route"] is True
        assert tun["strict_route"] is True
        assert tun["mtu"] == 1420

    def test_dns_is_ipv4_only(self, service):
        """DNS strategy forces IPv4-only and no AAAA query rule is emitted."""
        cfg = self._config(service)
        assert cfg["dns"]["strategy"] == "ipv4_only"
        rules = cfg["dns"]["rules"]
        assert not any(r.get("query_type") == ["A", "AAAA"] for r in rules)
        assert not any("AAAA" in r.get("query_type", []) for r in rules)

    def test_proxy_outbound_points_at_xray_socks(self, service):
        """The proxy outbound targets Xray's SOCKS port."""
        cfg = self._config(service, socks_port=10805)
        proxy = next(o for o in cfg["outbounds"] if o["tag"] == "proxy")
        assert proxy["type"] == "socks"
        assert proxy["server"] == "127.0.0.1"
        assert proxy["server_port"] == 10805

    def test_user_routing_rules_applied(self, service):
        """User direct/proxy/block rules are injected into route rules."""
        cfg = self._config(
            service,
            routing_rules={
                "direct": ["direct.com"],
                "proxy": ["proxy.com"],
                "block": ["block.com"],
            },
        )
        outbounds = [r.get("outbound") for r in cfg["route"]["rules"]]
        assert "direct" in outbounds
        assert "proxy" in outbounds
        assert "block" in outbounds

    def test_hijack_dns_rule_present(self, service):
        """DNS hijacking rule ensures all DNS goes through the tunnel."""
        cfg = self._config(service)
        hijack = [r for r in cfg["route"]["rules"] if r.get("action") == "hijack-dns"]
        assert hijack, "Expected a hijack-dns rule"
        assert hijack[0]["protocol"] == "dns"

    def test_public_dns_resolvers_not_direct_routed(self, service):
        """1.1.1.1 and 8.8.8.8 must never be sent to the 'direct' outbound.

        A direct rule for a public DNS IP would bypass the TUN's hijack-dns
        interception, re-enabling ISP-level DNS tampering on raw sockets.
        """
        cfg = self._config(
            service,
            proxy_server_ip="1.2.3.4",
        )
        rules = cfg["route"]["rules"]
        direct_cidrs = [
            r.get("ip_cidr") for r in rules if r.get("outbound") == "direct" and isinstance(r.get("ip_cidr"), str)
        ]
        assert "1.1.1.1/32" not in direct_cidrs
        assert "8.8.8.8/32" not in direct_cidrs

        # The proxy server IP bypass is still injected (Wintun loop break)
        assert "1.2.3.4/32" in direct_cidrs

    def test_all_dns_traffic_flows_to_hijack_dns(self, service):
        """Port 53 is sniffed and DNS protocol is hijacked before any outbound match."""
        cfg = self._config(service)
        rules = cfg["route"]["rules"]
        # Rule order matters: sniff (port 53) must precede hijack-dns, which must
        # precede any direct/proxy outbound rule so DNS never hits 'direct'.
        actions = [(r.get("action"), r.get("protocol"), r.get("port")) for r in rules]
        # There are two sniff rules: general (no port) for TLS/HTTP SNI, and
        # port-53 specifically for DNS detection.  The port-53 sniff must
        # precede hijack-dns.
        sniff53_idx = next(
            i for i, a in enumerate(actions)
            if a[0] == "sniff" and a[2] == [53]
        )
        hijack_idx = next(i for i, a in enumerate(actions) if a[0] == "hijack-dns")
        assert sniff53_idx < hijack_idx, "port-53 sniff must precede hijack-dns"
        assert actions[hijack_idx][1] == "dns", "hijack-dns must match dns protocol"


class TestHelpers:
    """Tests for the ported helper methods."""

    def test_normalize_list_lowercases(self, service):
        assert service._normalize_list(["Example.com", "DNS.Google"]) == [
            "example.com",
            "dns.google",
        ]

    def test_normalize_list_handles_none(self, service):
        assert service._normalize_list(None) == []
        assert service._normalize_list("") == []

    def test_filter_real_ips(self, service):
        ips = service._filter_real_ips(["1.1.1.1", "2606:4700:4700::1111", "not-an-ip"])
        assert ips == ["1.1.1.1", "2606:4700:4700::1111"]

    def test_filter_domains(self, service):
        assert service._filter_domains(["1.1.1.1", "proxy.example.com"]) == ["proxy.example.com"]


class TestStaticRouteFiltering:
    """System static routes must never target DNS endpoints or private IPs."""

    def test_is_private_or_reserved(self, service):
        """RFC1918 + loopback + link-local are private; public IPs are not."""
        for private in (
            "10.0.0.1",
            "10.10.34.35",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.1.1",
            "127.0.0.1",
            "169.254.169.254",
        ):
            assert service._is_private_or_reserved(private) is True, private
        for public in ("1.1.1.1", "8.8.8.8", "104.16.72.94", "104.17.121.70"):
            assert service._is_private_or_reserved(public) is False, public

    def test_add_static_route_skips_private_ip(self, service):
        """Private/reserved IPs never produce a system static route."""
        with patch("subprocess.run") as mock_run:
            service._add_static_route("10.10.34.35", "192.168.1.1")
            service._add_static_route("192.168.5.5", "192.168.1.1")
            service._add_static_route("172.20.0.5", "192.168.1.1")
        mock_run.assert_not_called()
        assert service._added_routes == []

    def test_add_static_route_allows_public_ip(self, service):
        """Public proxy-server IPs still get a static route (Wintun loop break)."""
        with patch("subprocess.run") as mock_run:
            service._add_static_route("104.16.72.94", "192.168.1.1")
        mock_run.assert_called_once()
        assert "104.16.72.94" in service._added_routes

    def test_start_bypass_targets_restricted_to_proxy_server(self):
        """Route bypass is built from proxy server nodes only — no DNS endpoints."""
        with patch("src.utils.process_utils.ProcessUtils.is_running", return_value=True):
            service = SingboxService()
        service._process = MagicMock()
        service._process.pid = 999

        with (
            patch("src.platform.factory._is_windows", return_value=True),
            patch(
                "src.platform.windows.network.WindowsNetworkAdapter.get_primary_interface",
                return_value=("Wi-Fi", "192.168.1.10", "192.168.1.0/24", "192.168.1.1"),
            ),
            patch("src.platform.windows.settings._suppress_smhr"),
            patch.object(service, "_wait_for_xray_ready", return_value=True),
            patch.object(service, "_write_config_and_start", return_value=True),
            patch(
                "src.services.connection.route_manager_service.RouteManagerService.resolve_ips",
                return_value=["104.17.121.70"],
            ) as mock_resolve,
            patch("src.services.connection.route_manager_service.RouteManagerService.add_static_route") as mock_route,
        ):
            service.start(
                xray_socks_port=10805,
                proxy_server_ip="1mobility.zenups.ir",
                routing_rules={
                    "direct": ["10.0.0.5", "192.168.1.5"],
                    "proxy": [],
                    "block": [],
                },
            )

        bypass_targets = mock_resolve.call_args[0][0]
        assert bypass_targets == ["1mobility.zenups.ir"]
        # DNS endpoints must never be resolved or statically routed
        assert "dns.google" not in bypass_targets
        assert "cloudflare-dns.com" not in bypass_targets
        assert "8.8.8.8" not in bypass_targets
        assert "1.1.1.1" not in bypass_targets
        # User direct IPs are handled by sing-box route rules, not OS routes
        assert "10.0.0.5" not in bypass_targets
        assert "192.168.1.5" not in bypass_targets
        # Only the proxy-server resolved IP gets the static route
        mock_route.assert_called_once_with("104.17.121.70", "192.168.1.1")


class TestCountryRuleSetProxy:
    """Country rule-sets must download via the tunneled proxy (not direct),
    otherwise censored networks FATAL the TUN engine at startup."""

    def test_country_ruleset_download_via_proxy(self, service):
        cfg = service._generate_config(
            socks_port=10805,
            proxy_server_ip="",
            routing_country="ir",
            routing_rules={"direct": [], "proxy": [], "block": []},
            mtu=1420,
        )
        rs = cfg["route"].get("rule_set", [])
        assert rs, "expected country rule-sets"
        for r in rs:
            assert r["download_detour"] == "proxy", r
