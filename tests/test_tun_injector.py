"""Tests for TunInjector."""
from unittest.mock import Mock

import pytest

from src.services.tun_injector import TunInjector


@pytest.fixture
def mock_routing():
    routing = Mock()
    routing.load_toggles.return_value = {
        "block_udp_443": True,
        "block_ads": True,
        "direct_private_ips": True,
    }
    routing.load_rules.return_value = {"direct": [], "proxy": [], "block": []}
    return routing


@pytest.fixture
def injector(mock_routing):
    ctx = Mock()
    ctx.routing = mock_routing
    return TunInjector(ctx)


# ---------------------------------------------------------------------------
# inject() — structural tests
# ---------------------------------------------------------------------------


class TestInject:
    """Tests for TunInjector.inject()."""

    def test_injects_tun_inbound(self, injector):
        config = {"inbounds": [], "routing": {"rules": []}}
        injector.inject(config, dns_servers=["1.1.1.1"])
        assert any(ib.get("protocol") == "tun" for ib in config["inbounds"])

    def test_tun_inbound_structure(self, injector):
        config = {"inbounds": [], "routing": {"rules": []}}
        injector.inject(config, dns_servers=["1.1.1.1", "8.8.8.8"], mtu=1400)
        tun = next(ib for ib in config["inbounds"] if ib["protocol"] == "tun")
        assert tun["tag"] == "tun"
        assert tun["settings"]["mtu"] == 1400
        assert tun["settings"]["dns"] == ["1.1.1.1", "8.8.8.8"]
        assert tun["settings"]["gateway"] == ["10.0.0.1/16"]
        assert tun["sniffing"]["enabled"] is True
        assert tun["sniffing"]["destOverride"] == ["http", "tls", "quic"]

    def test_tun_prepended_to_inbounds(self, injector):
        config = {
            "inbounds": [
                {"tag": "socks", "protocol": "socks", "port": 10808},
            ],
            "routing": {"rules": []},
        }
        injector.inject(config, dns_servers=["1.1.1.1"])
        assert config["inbounds"][0]["protocol"] == "tun"
        assert config["inbounds"][1]["protocol"] == "socks"

    def test_replaces_existing_tun(self, injector):
        config = {
            "inbounds": [
                {"tag": "tun", "protocol": "tun", "settings": {"mtu": 9000}},
                {"tag": "socks", "protocol": "socks"},
            ],
            "routing": {"rules": []},
        }
        injector.inject(config, dns_servers=["1.1.1.1"], mtu=1400)
        tun_inbounds = [ib for ib in config["inbounds"] if ib["protocol"] == "tun"]
        assert len(tun_inbounds) == 1
        assert tun_inbounds[0]["settings"]["mtu"] == 1400

    def test_creates_inbounds_list_if_missing(self, injector):
        config = {}
        injector.inject(config, dns_servers=["1.1.1.1"])
        assert "inbounds" in config
        assert config["inbounds"][0]["protocol"] == "tun"

    def test_sets_domain_strategy(self, injector):
        config = {"inbounds": [], "routing": {"rules": []}}
        injector.inject(config, dns_servers=["1.1.1.1"])
        assert config["routing"]["domainStrategy"] == "IPIfNonMatch"

    def test_prepends_rules_to_existing(self, injector):
        config = {
            "inbounds": [],
            "routing": {
                "rules": [
                    {"type": "field", "outboundTag": "existing"},
                ]
            },
        }
        injector.inject(config, dns_servers=["1.1.1.1"])
        assert config["routing"]["rules"][-1]["outboundTag"] == "existing"

    def test_creates_routing_section_if_missing(self, injector):
        config = {"inbounds": []}
        injector.inject(config, dns_servers=["1.1.1.1"])
        assert "routing" in config
        assert "rules" in config["routing"]


# ---------------------------------------------------------------------------
# _build_routing_rules() — rule ordering and content
# ---------------------------------------------------------------------------


class TestBuildRoutingRules:
    """Tests for TunInjector._build_routing_rules()."""

    def test_proxy_server_ips_go_direct(self, injector):
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": [], "proxy": [], "block": []},
            proxy_server_ips=["1.1.1.1", "2.2.2.2"],
        )
        ip_rule = next(r for r in rules if "ip" in r and r.get("outboundTag") == "direct")
        assert "1.1.1.1" in ip_rule["ip"]

    def test_proxy_server_domains_go_direct(self, injector):
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": [], "proxy": [], "block": []},
            proxy_server_ips=["proxy.example.com"],
        )
        domain_rule = next(r for r in rules if "domain" in r and r.get("outboundTag") == "direct")
        assert "proxy.example.com" in domain_rule["domain"]

    def test_user_block_rules(self, injector):
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": [], "proxy": [], "block": ["bad.com"]},
            proxy_server_ips=[],
        )
        block_rule = next(r for r in rules if r.get("outboundTag") == "block")
        assert "bad.com" in block_rule["domain"]

    def test_block_udp_443_when_enabled(self, injector):
        injector._app_context.routing.load_toggles.return_value = {
            "block_udp_443": True,
            "block_ads": False,
            "direct_private_ips": False,
        }
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": [], "proxy": [], "block": []},
            proxy_server_ips=[],
        )
        udp_rule = next(r for r in rules if r.get("network") == "udp" and r.get("outboundTag") == "block")
        assert udp_rule["port"] == "443"

    def test_block_udp_443_skipped_when_disabled(self, injector):
        injector._app_context.routing.load_toggles.return_value = {
            "block_udp_443": False,
            "block_ads": False,
            "direct_private_ips": False,
        }
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": [], "proxy": [], "block": []},
            proxy_server_ips=[],
        )
        udp_rules = [r for r in rules if r.get("network") == "udp" and r.get("outboundTag") == "block"]
        assert len(udp_rules) == 0

    def test_block_ads_when_enabled(self, injector):
        injector._app_context.routing.load_toggles.return_value = {
            "block_udp_443": False,
            "block_ads": True,
            "direct_private_ips": False,
        }
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": [], "proxy": [], "block": []},
            proxy_server_ips=[],
        )
        ads_rule = next(r for r in rules if "geosite:category-ads-all" in r.get("domain", []))
        assert ads_rule["outboundTag"] == "block"

    def test_block_ads_skipped_when_disabled(self, injector):
        injector._app_context.routing.load_toggles.return_value = {
            "block_udp_443": False,
            "block_ads": False,
            "direct_private_ips": False,
        }
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": [], "proxy": [], "block": []},
            proxy_server_ips=[],
        )
        ads_rules = [r for r in rules if "geosite:category-ads-all" in str(r.get("domain", []))]
        assert len(ads_rules) == 0

    def test_user_direct_rules(self, injector):
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": ["direct.com"], "proxy": [], "block": []},
            proxy_server_ips=[],
        )
        direct_rule = next(r for r in rules if r.get("outboundTag") == "direct" and "domain" in r)
        assert "direct.com" in direct_rule["domain"]

    def test_private_ips_go_direct_when_enabled(self, injector):
        injector._app_context.routing.load_toggles.return_value = {
            "block_udp_443": False,
            "block_ads": False,
            "direct_private_ips": True,
        }
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": [], "proxy": [], "block": []},
            proxy_server_ips=[],
        )
        private_rule = next(r for r in rules if "geoip:private" in r.get("ip", []))
        assert private_rule["outboundTag"] == "direct"

    def test_private_ips_skipped_when_disabled(self, injector):
        injector._app_context.routing.load_toggles.return_value = {
            "block_udp_443": False,
            "block_ads": False,
            "direct_private_ips": False,
        }
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": [], "proxy": [], "block": []},
            proxy_server_ips=[],
        )
        private_rules = [r for r in rules if "geoip:private" in str(r.get("ip", []))]
        assert len(private_rules) == 0

    def test_country_rules_added(self, injector):
        rules = injector._build_routing_rules(
            routing_country="ir",
            routing_rules={"direct": [], "proxy": [], "block": []},
            proxy_server_ips=[],
        )
        country_ip_rule = next(r for r in rules if any("geoip:ir" in str(ip) for ip in r.get("ip", [])))
        assert country_ip_rule["outboundTag"] == "direct"

    def test_country_empty_skipped(self, injector):
        injector._app_context.routing.load_toggles.return_value = {
            "block_udp_443": False,
            "block_ads": False,
            "direct_private_ips": False,
        }
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": [], "proxy": [], "block": []},
            proxy_server_ips=[],
        )
        country_rules = [
            r for r in rules if any("geoip:" in str(ip) and "private" not in str(ip) for ip in r.get("ip", []))
        ]
        assert len(country_rules) == 0

    def test_user_proxy_rules(self, injector):
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": [], "proxy": ["proxy.com"], "block": []},
            proxy_server_ips=[],
        )
        proxy_rule = next(r for r in rules if r.get("outboundTag") == "proxy")
        assert "proxy.com" in proxy_rule["domain"]

    def test_default_routing_with_no_toggles(self, injector):
        injector._app_context.routing.load_toggles.return_value = {}
        rules = injector._build_routing_rules(
            routing_country="",
            routing_rules={"direct": ["a.com"], "proxy": [], "block": []},
            proxy_server_ips=[],
        )
        direct_rule = next(r for r in rules if r.get("outboundTag") == "direct" and "domain" in r)
        assert "a.com" in direct_rule["domain"]

    def test_routing_order_respected(self, injector):
        injector._app_context.routing.load_toggles.return_value = {
            "block_udp_443": True,
            "block_ads": True,
            "direct_private_ips": True,
        }
        rules = injector._build_routing_rules(
            routing_country="ir",
            routing_rules={
                "direct": ["d.com"],
                "proxy": ["p.com"],
                "block": ["b.com"],
            },
            proxy_server_ips=["5.5.5.5"],
        )
        tags = [r.get("outboundTag") for r in rules]
        assert tags[0] == "direct"  # proxy server IPs
        assert tags[-1] == "proxy"  # user proxy rules at end
