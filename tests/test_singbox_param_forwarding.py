"""Regression tests for singbox routing parameter forwarding chain.

Bug: singbox_service.start() received routing_country but never
forwarded it to config_builder.build(). Country rules were silently
dropped.

Covers:
  1. routing_country forwarded from start() to build()
  2. Config has country rule-sets when routing_country is set
  3. Config has NO country rule-sets when routing_country is empty
  4. User routing rules (domain_suffix) appear in output
  5. sniff + resolve actions present in route rules
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.core.config_builders.singbox_config_builder import SingboxConfigBuilder

# -- helpers -------------------------------------------------------


def _build(overrides=None):
    b = SingboxConfigBuilder()
    kw = dict(
        socks_port=10805,
        proxy_server_ip="5.6.7.8",
        routing_country="",
        interface_name="utun0",
        routing_rules=None,
        mtu=1420,
        local_dns_server="192.168.1.1",
        sni_connect_ip=None,
        toggles=None,
    )
    if overrides:
        kw.update(overrides)
    return b.build(**kw)


# -- 1. routing_country forwarding ---------------------------------


class TestRoutingCountryForwarding:
    def test_ir_country_adds_rule_sets(self):
        cfg = _build(dict(routing_country="ir"))
        rs_tags = [r["tag"] for r in cfg["route"].get("rule_set", [])]
        assert "ir-rules-0" in rs_tags, f"missing geoip rule_set, got: {rs_tags}"
        assert "ir-rules-1" in rs_tags, f"missing geosite rule_set, got: {rs_tags}"

    def test_ir_country_adds_route_rules(self):
        cfg = _build(dict(routing_country="ir"))
        rule_tags = [r.get("rule_set") for r in cfg["route"]["rules"]]
        assert "ir-rules-0" in rule_tags, "geoip rule missing"
        assert "ir-rules-1" in rule_tags, "geosite rule missing"

    def test_ir_country_adds_dns_rules(self):
        cfg = _build(dict(routing_country="ir"))
        dns_rs = [r.get("rule_set") for r in cfg["dns"].get("rules", [])]
        assert "ir-rules-0" in dns_rs, "geoip DNS rule missing"
        assert "ir-rules-1" in dns_rs, "geosite DNS rule missing"

    def test_empty_country_no_rules(self):
        cfg = _build(dict(routing_country=""))
        rs_tags = [r["tag"] for r in cfg["route"].get("rule_set", [])]
        assert not any("ir-rules" in t for t in rs_tags)

    def test_none_country_no_rules(self):
        cfg = _build(dict(routing_country=None))
        rs_tags = [r["tag"] for r in cfg["route"].get("rule_set", [])]
        assert not any("ir-rules" in t for t in rs_tags)

    def test_unknown_country_no_crash(self):
        cfg = _build(dict(routing_country="zz"))
        rs_tags = [r["tag"] for r in cfg["route"].get("rule_set", [])]
        assert not any("zz" in t for t in rs_tags)


# -- 2. routing_rules forwarding -----------------------------------


class TestRoutingRulesForwarding:
    def test_direct_domain_appears(self):
        rules = {"direct": ["example.com"], "proxy": [], "block": []}
        cfg = _build(dict(routing_rules=rules))
        ds = [r.get("domain_suffix") for r in cfg["route"]["rules"]]
        assert ["example.com"] in ds, f"domain_suffix not found: {ds}"

    def test_proxy_domain_appears(self):
        rules = {"direct": [], "proxy": ["openai.com"], "block": []}
        cfg = _build(dict(routing_rules=rules))
        ds = [r.get("domain_suffix") for r in cfg["route"]["rules"]]
        assert ["openai.com"] in ds

    def test_block_domain_appears(self):
        rules = {"direct": [], "proxy": [], "block": ["ads.example.com"]}
        cfg = _build(dict(routing_rules=rules))
        ds = [r.get("domain_suffix") for r in cfg["route"]["rules"]]
        assert ["ads.example.com"] in ds

    def test_direct_ip_appears(self):
        rules = {"direct": ["10.0.0.1/32"], "proxy": [], "block": []}
        cfg = _build(dict(routing_rules=rules))
        ips = [r.get("ip_cidr") for r in cfg["route"]["rules"]]
        assert ["10.0.0.1/32"] in ips

    def test_no_rules_no_domain_suffix(self):
        cfg = _build(dict(routing_rules=None))
        ds = [r.get("domain_suffix") for r in cfg["route"]["rules"]]
        assert all(d is None for d in ds)


# -- 3. sniff + resolve actions ------------------------------------


class TestSniffAndResolveActions:
    def test_sniff_action_present(self):
        cfg = _build()
        actions = [r.get("action") for r in cfg["route"]["rules"]]
        assert "sniff" in actions

    def test_resolve_action_present(self):
        cfg = _build()
        actions = [r.get("action") for r in cfg["route"]["rules"]]
        assert "resolve" in actions

    def test_sniff_before_resolve(self):
        cfg = _build()
        sniff_idx = next(
            i for i, r in enumerate(cfg["route"]["rules"]) if r.get("action") == "sniff" and not r.get("port")
        )
        resolve_idx = next(i for i, r in enumerate(cfg["route"]["rules"]) if r.get("action") == "resolve")
        assert sniff_idx < resolve_idx

    def test_resolve_before_domain_rules(self):
        cfg = _build(dict(routing_rules={"direct": ["test.com"], "proxy": [], "block": []}))
        resolve_idx = next(i for i, r in enumerate(cfg["route"]["rules"]) if r.get("action") == "resolve")
        domain_idx = next(i for i, r in enumerate(cfg["route"]["rules"]) if r.get("domain_suffix") == ["test.com"])
        assert resolve_idx < domain_idx


# -- 4. singbox_service forwards routing_country -------------------


class TestSingboxServiceForwardsRoutingCountry:
    @patch("src.services.core_engines.singbox_service.SingboxService._wait_for_xray_ready")
    @patch("src.services.core_engines.singbox_service.SingboxService._write_config_and_start")
    def test_start_forwards_routing_country(self, _wcfg, _wait):
        _wait.return_value = True
        _wcfg.return_value = True
        from src.services.core_engines.singbox_service import SingboxService

        svc = SingboxService.__new__(SingboxService)
        svc._config_builder = MagicMock()
        svc._process_manager = MagicMock()
        svc._route_manager = MagicMock()
        svc._smhr_was_enabled = False
        svc._config_builder.build.return_value = {
            "inbounds": [],
            "outbounds": [{"type": "direct", "tag": "direct"}],
            "route": {"rules": [], "final": "direct"},
            "dns": {"servers": [], "rules": []},
        }
        svc._config_builder.validate_config.return_value = True
        svc._process_manager.start_process.return_value = 1234
        svc._proc = MagicMock()
        svc._proc.close_log = MagicMock()

        svc.start(
            xray_socks_port=10805,
            proxy_server_ip="5.6.7.8",
            routing_country="ir",
            routing_rules={"direct": [], "proxy": [], "block": []},
            routing_toggles={},
        )

        svc._config_builder.build.assert_called_once()
        call_kw = svc._config_builder.build.call_args[1]
        assert call_kw.get("routing_country") == "ir", f"routing_country not forwarded: {list(call_kw.keys())}"

    @patch("src.services.core_engines.singbox_service.SingboxService._wait_for_xray_ready")
    @patch("src.services.core_engines.singbox_service.SingboxService._write_config_and_start")
    def test_start_always_forwards_routing_country(self, _wcfg, _wait):
        _wait.return_value = True
        _wcfg.return_value = True
        from src.services.core_engines.singbox_service import SingboxService

        svc = SingboxService.__new__(SingboxService)
        svc._config_builder = MagicMock()
        svc._process_manager = MagicMock()
        svc._route_manager = MagicMock()
        svc._smhr_was_enabled = False
        svc._config_builder.build.return_value = {
            "inbounds": [],
            "outbounds": [{"type": "direct", "tag": "direct"}],
            "route": {"rules": [], "final": "direct"},
            "dns": {"servers": [], "rules": []},
        }
        svc._config_builder.validate_config.return_value = True
        svc._process_manager.start_process.return_value = 1234
        svc._proc = MagicMock()
        svc._proc.close_log = MagicMock()

        svc.start(
            xray_socks_port=10805,
            proxy_server_ip="5.6.7.8",
            routing_country="",
            routing_rules=None,
            routing_toggles=None,
        )

        call_kw = svc._config_builder.build.call_args[1]
        assert "routing_country" in call_kw, "routing_country must always be forwarded (even when empty)"
