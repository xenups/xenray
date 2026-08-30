"""Unit tests for specialized sing-box builders and injectors."""

import pytest

from src.core.singbox.builders.country_rules_injector import CountryRulesInjector
from src.core.singbox.builders.dns_config_builder import DnsConfigBuilder
from src.core.singbox.builders.route_config_builder import RouteConfigBuilder
from src.core.singbox.builders.user_rules_injector import UserRulesInjector
from src.utils.network_utils import NetworkUtils


class TestNetworkUtilsHelpers:
    """Test static network utilities extracted from SingboxConfigBuilder."""

    def test_normalize_list(self):
        assert NetworkUtils.normalize_list(None) == []
        assert NetworkUtils.normalize_list("  'Example.COM' ") == ["example.com"]
        assert NetworkUtils.normalize_list([" [Foo.Bar] ", "BAZ"]) == ["foo.bar", "baz"]

    def test_filter_real_ips(self):
        entries = ["1.1.1.1", "google.com", "2606:4700:4700::1111", "invalid-ip", "8.8.8.8"]
        ips = NetworkUtils.filter_real_ips(entries)
        assert ips == ["1.1.1.1", "2606:4700:4700::1111", "8.8.8.8"]

    def test_filter_domains(self):
        entries = ["1.1.1.1", "google.com", "2606:4700:4700::1111", "sub.domain.org", "8.8.8.8"]
        domains = NetworkUtils.filter_domains(entries)
        assert domains == ["google.com", "sub.domain.org"]

    def test_is_valid_ip_cidr(self):
        assert NetworkUtils.is_valid_ip_cidr("192.168.1.1") is True
        assert NetworkUtils.is_valid_ip_cidr("10.0.0.0/24") is True
        assert NetworkUtils.is_valid_ip_cidr("2001:db8::/32") is True
        assert NetworkUtils.is_valid_ip_cidr("not-an-ip") is False

    def test_is_ipv4(self):
        assert NetworkUtils.is_ipv4("192.168.1.1") is True
        assert NetworkUtils.is_ipv4("::1") is False
        assert NetworkUtils.is_ipv4("example.com") is False


class TestDnsConfigBuilder:
    """Test DnsConfigBuilder behavior."""

    def test_build_dns_structure(self):
        builder = DnsConfigBuilder()
        dns = builder.build(local_dns_server="192.168.1.1")

        assert dns["strategy"] == "ipv4_only"
        assert dns["final"] == "remote_proxy"
        assert len(dns["servers"]) == 3
        tags = [s["tag"] for s in dns["servers"]]
        assert "bootstrap" in tags
        assert "local_dns" in tags
        assert "remote_proxy" in tags

        local_server = next(s for s in dns["servers"] if s["tag"] == "local_dns")
        assert local_server["server"] == "192.168.1.1"


class TestRouteConfigBuilder:
    """Test RouteConfigBuilder behavior."""

    def test_build_inbounds(self):
        builder = RouteConfigBuilder()
        inbounds = builder.build_inbounds(mtu=1350)
        assert len(inbounds) == 1
        assert inbounds[0]["type"] == "tun"
        assert inbounds[0]["mtu"] == 1350

    def test_build_outbounds(self):
        builder = RouteConfigBuilder()
        outbounds = builder.build_outbounds(socks_port=10808, interface_name="eth0")
        tags = {o["tag"]: o for o in outbounds}
        assert "proxy" in tags
        assert "direct" in tags
        assert tags["direct"]["type"] == "direct"
        assert "bind_interface" not in tags["direct"], "direct outbound must remain interface-agnostic"
        assert "block" in tags

    def test_inject_loop_breakers(self):
        builder = RouteConfigBuilder()
        base_route = builder.build_base_route()
        rules = base_route["rules"]
        dns_rules = []

        idx = builder.inject_loop_breakers(
            rules=rules,
            dns_rules=dns_rules,
            proxy_ips=["93.184.216.34"],
            proxy_domains=["proxy.example.com"],
            sni_connect_ip="185.193.30.94",
        )

        assert idx > 0
        direct_ips = [r for r in rules if r.get("ip_cidr") == "93.184.216.34/32"]
        assert len(direct_ips) == 1
        direct_domains = [r for r in rules if r.get("domain_suffix") == "proxy.example.com"]
        assert len(direct_domains) == 1
        sni_rules = [r for r in rules if r.get("ip_cidr") == "185.193.30.94"]
        assert len(sni_rules) == 1


class TestUserRulesInjector:
    """Test UserRulesInjector behavior."""

    def test_inject_user_rules(self):
        injector = UserRulesInjector()
        rules = [{"action": "sniff"}, {"action": "hijack-dns"}]
        dns_rules = []
        cfg_route = {}

        injector.inject(
            rules=rules,
            dns_rules=dns_rules,
            routing_rules={"direct": ["mysite.ir"], "block": ["ads.evil.com"]},
            toggles={"block_ads": True, "block_udp_443": True},
            insert_index=1,
            cfg_route=cfg_route,
        )

        # Check injected route rules
        assert any(r.get("domain_suffix") == ["mysite.ir"] and r.get("outbound") == "direct" for r in rules)
        assert any(r.get("domain_suffix") == ["ads.evil.com"] and r.get("outbound") == "block" for r in rules)
        assert any(r.get("network") == "udp" and r.get("port") == 443 and r.get("outbound") == "block" for r in rules)

        # Check injected DNS reject rules
        assert any(r.get("action") == "reject" and r.get("domain_suffix") == ["ads.evil.com"] for r in dns_rules)
        assert any(r.get("server") == "local_dns" and r.get("domain_suffix") == ["mysite.ir"] for r in dns_rules)


class TestCountryRulesInjector:
    """Test CountryRulesInjector behavior."""

    def test_inject_country_rules(self):
        injector = CountryRulesInjector()
        cfg_route = {"rules": []}
        dns_rules = []

        injector.inject(cfg_route=cfg_route, dns_rules=dns_rules, routing_country="ir")

        assert "rule_set" in cfg_route
        assert len(cfg_route["rule_set"]) >= 1
        assert any(r.get("outbound") == "direct" for r in cfg_route["rules"])
        assert any(r.get("server") == "bootstrap" for r in dns_rules)
