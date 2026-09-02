"""Unit tests for Block routing rules in Sing-box and Xray."""

from unittest.mock import Mock

from src.core.config_builders.singbox_config_builder import SingboxConfigBuilder
from src.services.connection.tun_injector import TunInjector
from src.services.core_engines.xray_config_processor import XrayConfigProcessor


class TestSingboxBlockRouting:
    """Verify that SingboxConfigBuilder properly handles 'block' rules in routing and DNS."""

    def test_block_domain_creates_reject_dns_rule_and_block_route(self):
        builder = SingboxConfigBuilder()
        cfg = builder.build(
            socks_port=10805,
            proxy_server_ip="1.2.3.4",
            routing_country="",
            routing_rules={
                "direct": ["varzesh3.com"],
                "proxy": [],
                "block": ["blocked-domain.com", "ads.example.com"],
            },
            mtu=1400,
        )

        dns_rules = cfg["dns"]["rules"]
        route_rules = cfg["route"]["rules"]

        # Check DNS reject rule for blocked domains
        reject_dns = [r for r in dns_rules if r.get("action") == "reject"]
        assert len(reject_dns) >= 1
        blocked_dns_suffixes = []
        for r in reject_dns:
            blocked_dns_suffixes.extend(r.get("domain_suffix", []))
        assert "blocked-domain.com" in blocked_dns_suffixes
        assert "ads.example.com" in blocked_dns_suffixes

        # Check Route block rule
        block_routes = [r for r in route_rules if r.get("outbound") == "block"]
        blocked_route_suffixes = []
        for r in block_routes:
            blocked_route_suffixes.extend(r.get("domain_suffix", []))
        assert "blocked-domain.com" in blocked_route_suffixes
        assert "ads.example.com" in blocked_route_suffixes

    def test_block_ip_creates_block_ip_cidr_route(self):
        builder = SingboxConfigBuilder()
        cfg = builder.build(
            socks_port=10805,
            proxy_server_ip="1.2.3.4",
            routing_country="",
            routing_rules={
                "direct": [],
                "proxy": [],
                "block": ["198.51.100.1", "203.0.113.0/24"],
            },
            mtu=1400,
        )

        route_rules = cfg["route"]["rules"]
        block_routes = [r for r in route_rules if r.get("outbound") == "block"]
        blocked_cidrs = []
        for r in block_routes:
            blocked_cidrs.extend(r.get("ip_cidr", []))
        assert "198.51.100.1" in blocked_cidrs
        assert "203.0.113.0/24" in blocked_cidrs

    def test_block_ads_toggle_creates_reject_dns_and_rule_set(self, tmp_path, monkeypatch):
        from src.core.singbox.builders import rule_set_utils

        (tmp_path / "geosite-category-ads-all.srs").write_bytes(b"x")
        monkeypatch.setattr(rule_set_utils, "_RULE_CACHE", str(tmp_path))

        builder = SingboxConfigBuilder()
        cfg = builder.build(
            socks_port=10805,
            proxy_server_ip="1.2.3.4",
            routing_country="",
            routing_rules={"direct": [], "proxy": [], "block": []},
            toggles={"block_ads": True, "block_udp_443": True},
            mtu=1400,
        )

        dns_rules = cfg["dns"]["rules"]
        reject_dns = [r for r in dns_rules if r.get("action") == "reject" and r.get("rule_set") == "ads-rules"]
        assert len(reject_dns) == 1

        route_rules = cfg["route"]["rules"]
        block_ads = [r for r in route_rules if r.get("outbound") == "block" and r.get("rule_set") == "ads-rules"]
        assert len(block_ads) == 1
        assert all(rs["type"] == "local" for rs in cfg["route"]["rule_set"])


class TestXrayBlockRouting:
    """Verify that Xray processor and TunInjector properly handle 'block' outbounds and rules."""

    def test_tun_injector_ensures_block_and_direct_outbounds(self):
        ctx = Mock()
        ctx.routing.load_toggles.return_value = {}
        ctx.settings.get_sni_spoof_enabled.return_value = False
        injector = TunInjector(ctx)

        config = {
            "inbounds": [],
            "outbounds": [{"protocol": "vless", "tag": "proxy"}],
            "routing": {"rules": []},
        }

        injector.inject(
            config,
            dns_servers=["1.1.1.1"],
            routing_rules={"direct": [], "proxy": [], "block": ["blocked.org", "1.2.3.4"]},
        )

        outbounds = config["outbounds"]
        tags = {ob["tag"]: ob["protocol"] for ob in outbounds}
        assert "direct" in tags
        assert tags["direct"] == "freedom"
        assert "block" in tags
        assert tags["block"] == "blackhole"

        rules = config["routing"]["rules"]
        block_rules = [r for r in rules if r.get("outboundTag") == "block"]
        assert any("blocked.org" in r.get("domain", []) for r in block_rules)
        assert any("1.2.3.4" in r.get("ip", []) for r in block_rules)

    def test_xray_config_processor_injects_block_rules_in_proxy_mode(self):
        ctx = Mock()
        ctx.settings.get_proxy_port.return_value = 10808
        ctx.settings.get_http_port.return_value = 10809
        ctx.settings.get_allow_lan.return_value = False
        ctx.settings.get_sni_spoof_enabled.return_value = False
        ctx.settings.get_cipher_suites.return_value = ""
        ctx.dns.load.return_value = []
        ctx.routing.load_rules.return_value = {
            "direct": ["local.net"],
            "proxy": [],
            "block": ["ads.server.com"],
        }
        ctx.routing.load_toggles.return_value = {"block_ads": True, "block_udp_443": True}

        processor = XrayConfigProcessor(ctx)
        base_config = {
            "inbounds": [],
            "outbounds": [
                {
                    "protocol": "vless",
                    "tag": "proxy",
                    "settings": {
                        "vnext": [{"address": "example.com", "port": 443}]
                    },
                }
            ],
            "routing": {"rules": []},
        }

        cfg = processor.process_config(base_config, mode="proxy")
        outbound_tags = {ob["tag"] for ob in cfg["outbounds"]}
        assert "direct" in outbound_tags
        assert "block" in outbound_tags

        rules = cfg["routing"]["rules"]
        block_rules = [r for r in rules if r.get("outboundTag") == "block"]
        assert any("ads.server.com" in r.get("domain", []) for r in block_rules)
        assert any("geosite:category-ads-all" in r.get("domain", []) for r in block_rules)
        assert any(r.get("network") == "udp" and r.get("port") == "443" for r in block_rules)
