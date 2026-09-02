"""Tests for TunInjector."""

from unittest.mock import Mock

import pytest

from src.core.constants import TUN_GATEWAY_IPV4, TUN_ROUTE_IPV4
from src.services.connection.tun_injector import TunInjector


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
    # Default: SNI spoof disabled (so existing routing-order tests keep
    # ds-out-first). Tests that need it enabled override this.
    ctx.settings = Mock()
    ctx.settings.get_sni_spoof_enabled.return_value = False
    ctx.settings.get_sni_connect_ip.return_value = "185.193.30.94"
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
        assert tun["settings"]["gateway"] == [TUN_GATEWAY_IPV4]
        assert tun["settings"]["autoSystemRoutingTable"] == [TUN_ROUTE_IPV4]
        assert tun["sniffing"]["enabled"] is True
        assert tun["sniffing"]["destOverride"] == ["fakedns", "http", "tls", "quic"]

    def test_tun_inbound_ipv4_only(self, injector):
        """TUN adapter is IPv4-only: single IPv4 subnet and default route."""
        config = {"inbounds": [], "routing": {"rules": []}}
        injector.inject(config, dns_servers=["1.1.1.1"])
        tun = next(ib for ib in config["inbounds"] if ib["protocol"] == "tun")
        gateway = tun["settings"]["gateway"]
        routes = tun["settings"]["autoSystemRoutingTable"]
        assert gateway == [TUN_GATEWAY_IPV4]
        assert routes == [TUN_ROUTE_IPV4]
        assert not any(":" in g for g in gateway), "No IPv6 gateway subnets allowed"

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
        assert config["routing"]["domainStrategy"] == "AsIs"

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
        domain_rules = [r for r in rules if "domain" in r and r.get("outboundTag") == "direct"]
        assert any("proxy.example.com" in r["domain"] for r in domain_rules)

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
        direct_rules = [r for r in rules if r.get("outboundTag") == "direct" and "domain" in r]
        assert any("direct.com" in r["domain"] for r in direct_rules)

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
        direct_rules = [r for r in rules if r.get("outboundTag") == "direct" and "domain" in r]
        assert any("a.com" in r["domain"] for r in direct_rules)

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
        assert tags[0] == "dns-out"  # DNS port 53 rule is first
        assert "direct" in tags
        # User proxy outranks country-direct: proxy rule must come BEFORE the
        # geoip:ir / geosite:ir country bypass (first-match-wins).
        proxy_idx = tags.index("proxy")
        ir_idx = next(i for i, t in enumerate(tags) if t == "direct" and "geoip:ir" in str(rules[i].get("ip", "")))
        assert proxy_idx < ir_idx, "user proxy must precede country direct"


def test_user_rules_inserted_before_hijack_dns():
    """User routing rules must be inserted BEFORE the sniff/hijack-dns chain
    (first-match-wins) so 'direct example.com' is not swallowed by hijack-dns."""
    from src.core.config_builders.singbox_config_builder import SingboxConfigBuilder

    builder = SingboxConfigBuilder.__new__(SingboxConfigBuilder)
    cfg = {
        "route": {
            "rules": [
                {"process_name": ["x"], "outbound": "direct"},
                {"protocol": "dns", "action": "hijack-dns"},
                {"ip_cidr": ["10.0.0.0/8"], "outbound": "direct"},
            ],
            "final": "proxy",
        },
        "dns": {"rules": []},
    }
    builder._apply_user_routing_rules(cfg, {"direct": ["example.com", "1.2.3.4"], "block": ["bad.com"]}, insert_at=1)

    rules = cfg["route"]["rules"]
    # Find the hijack-dns index
    hijack_idx = next(i for i, r in enumerate(rules) if r.get("action") == "hijack-dns")
    # User domain/IP rules must appear BEFORE hijack-dns
    user_idxs = [
        i for i, r in enumerate(rules) if "example.com" in str(r) or "1.2.3.4" in str(r) or "bad.com" in str(r)
    ]
    assert user_idxs, "user rules missing"
    assert all(i < hijack_idx for i in user_idxs), f"user rules {user_idxs} must precede hijack-dns {hijack_idx}"
    # DNS bootstrap rule for direct domain → local_dns (not foreign 8.8.8.8)
    dns_rules = cfg["dns"]["rules"]
    assert any("example.com" in str(r) and r.get("server") == "local_dns" for r in dns_rules)


def test_sni_spoof_connect_ip_goes_direct(injector):
    """When SNI spoof is enabled, CONNECT_IP routes through the direct outbound
    (loop-breaker) as the FIRST rule."""
    injector._app_context.settings.get_sni_spoof_enabled.return_value = True
    injector._app_context.settings.get_sni_connect_ip.return_value = "185.193.30.94"
    rules = injector._build_routing_rules("", {"direct": [], "proxy": [], "block": []}, ["5.5.5.5"])
    assert rules[0]["outboundTag"] == "direct"
    assert "185.193.30.94" in rules[0]["ip"]


def test_singbox_builder_applies_routing_toggles(tmp_path, monkeypatch):
    """block_udp_443 / block_ads toggles must reach the sing-box TUN config
    (previously they only applied to the Xray-TUN engine path)."""
    from src.core.config_builders.singbox_config_builder import SingboxConfigBuilder
    from src.core.singbox.builders import rule_set_utils

    (tmp_path / "geosite-category-ads-all.srs").write_bytes(b"x")
    monkeypatch.setattr(rule_set_utils, "_RULE_CACHE", str(tmp_path))

    builder = SingboxConfigBuilder()
    cfg = builder.build(
        socks_port=10805,
        proxy_server_ip="5.5.5.5",
        routing_country="",
        interface_name="eth0",
        routing_rules={"direct": [], "proxy": [], "block": []},
        mtu=1420,
        local_dns_server="192.168.1.1",
        sni_connect_ip=None,
        toggles={"block_udp_443": True, "block_ads": True},
    )

    rules = cfg["route"]["rules"]
    quic_block = [r for r in rules if r.get("network") == "udp" and r.get("port") == 443]
    ads_block = [r for r in rules if r.get("rule_set") == "ads-rules"]
    assert any(r.get("outbound") == "block" for r in quic_block)
    assert any(r.get("outbound") == "block" for r in ads_block)
    assert any(rs["tag"] == "ads-rules" for rs in cfg["route"]["rule_set"])


def test_singbox_builder_without_toggles_no_extra_rules():
    """Toggles disabled → no QUIC block, no ads rule-set emitted."""
    from src.core.config_builders.singbox_config_builder import SingboxConfigBuilder

    builder = SingboxConfigBuilder()
    cfg = builder.build(
        socks_port=10805,
        proxy_server_ip="5.5.5.5",
        routing_country="",
        interface_name="eth0",
        routing_rules={"direct": [], "proxy": [], "block": []},
        mtu=1420,
        local_dns_server="192.168.1.1",
        sni_connect_ip=None,
        toggles={"block_udp_443": False, "block_ads": False},
    )

    rules = cfg["route"]["rules"]
    # The default udp/443→proxy rule exists; no udp/443→block may exist.
    quic = [r for r in rules if r.get("network") == "udp" and r.get("port") == 443]
    assert all(r.get("outbound") != "block" for r in quic)
    assert not [r for r in rules if r.get("rule_set") == "ads-rules"]


def test_singbox_dns_rules_user_domains_before_catchall():
    """User direct domains MUST be resolved by local_dns, not remote_proxy.
    DNS rules are first-match-wins — the catch-all inbound:[tun-in] rule
    must come AFTER user domain-specific rules."""
    from src.core.config_builders.singbox_config_builder import SingboxConfigBuilder

    cfg = SingboxConfigBuilder().build(
        socks_port=10805,
        proxy_server_ip="5.5.5.5",
        routing_country="none",
        interface_name="eth0",
        routing_rules={"direct": ["ikco.ir", "bmi.ir"], "proxy": [], "block": []},
        mtu=1420,
        local_dns_server="192.168.1.1",
        sni_connect_ip=None,
    )

    dns_rules = cfg["dns"]["rules"]
    # User domain rule must come BEFORE the catch-all
    user_idx = next(i for i, r in enumerate(dns_rules) if r.get("domain_suffix") == ["ikco.ir", "bmi.ir"])
    catchall_idx = next(i for i, r in enumerate(dns_rules) if r.get("inbound") == ["tun-in"] and "server" in r)
    assert (
        user_idx < catchall_idx
    ), f"user domain DNS rule (idx {user_idx}) must come before catch-all (idx {catchall_idx})"


def test_singbox_has_tls_sniff_for_domain_routing():
    """TLS/HTTP sniff must be present so domain-based route rules match
    HTTPS traffic even when the browser uses DoH (bypasses sing-box DNS)."""
    from src.core.config_builders.singbox_config_builder import SingboxConfigBuilder

    cfg = SingboxConfigBuilder().build(
        socks_port=10805,
        proxy_server_ip="5.5.5.5",
        routing_country="none",
        interface_name="eth0",
        routing_rules={"direct": [], "proxy": [], "block": []},
        mtu=1420,
        local_dns_server="192.168.1.1",
        sni_connect_ip=None,
    )

    route_rules = cfg["route"]["rules"]
    sniff = [r for r in route_rules if r.get("action") == "sniff" and r.get("inbound") == ["tun-in"]]
    assert sniff, "no TUN sniff rule found in route.rules"
    # Must have at least one sniff without port filter (covers TLS/HTTP)
    general_sniff = [r for r in sniff if "port" not in r]
    assert general_sniff, "no general (non-port-53) sniff rule — HTTPS SNI won't be extracted"
