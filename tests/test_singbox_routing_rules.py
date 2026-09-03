"""Sing-box routing + DNS rule ordering and integrity tests.

Covers the class of bugs found during manual QA:
  1. Country DNS rules silently swallowed by catch-all before them
  2. User direct domains resolved via remote_proxy instead of local_dns
  3. Sniff rule placed after domain rules → SNI never extracted
  4. Toggles (block QUIC / ads) not wired to sing-box path
  5. Rule-set paths with '..' segments rejected by sing-box
  6. sniff_override_destination rejected by sing-box 1.13
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from src.core.config_builders.singbox_config_builder import SingboxConfigBuilder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build(**overrides):
    """Build a sing-box config with sensible defaults for testing."""
    defaults = dict(
        socks_port=10805,
        proxy_server_ip="203.0.113.7",
        routing_country="none",
        interface_name="eth0",
        routing_rules={"direct": [], "proxy": [], "block": []},
        mtu=1420,
        local_dns_server="192.168.1.1",
        sni_connect_ip=None,
        toggles={"block_udp_443": False, "block_ads": False},
    )
    defaults.update(overrides)
    return SingboxConfigBuilder().build(**defaults)


def _dns_tags(cfg):
    """Return ordered list of (server_tag, match_key) for each DNS rule."""
    result = []
    for r in cfg["dns"]["rules"]:
        if "rule_set" in r:
            result.append((r["server"], "rule_set:" + r["rule_set"]))
        elif "domain_suffix" in r:
            result.append((r["server"], "suffix:" + str(r["domain_suffix"])))
        elif "inbound" in r:
            result.append((r["server"], "inbound:" + str(r["inbound"])))
    return result


def _route_outbounds(cfg):
    """Return list of outbound tags in route rule order."""
    return [r.get("outbound") or r.get("action") or "?" for r in cfg["route"]["rules"]]


# ===========================================================================
# DNS RULE ORDERING
# ===========================================================================


class TestDnsRuleOrdering:
    """Catch-all DNS rule must never precede user or country rules."""

    def test_user_direct_before_catchall(self):
        """ikco.ir must resolve via local_dns, not remote_proxy."""
        cfg = _build(routing_rules={"direct": ["ikco.ir"], "proxy": [], "block": []})
        tags = _dns_tags(cfg)
        user_idx = next(i for i, (_, k) in enumerate(tags) if "ikco.ir" in k)
        catchall_idx = next(i for i, (_, k) in enumerate(tags) if k.startswith("inbound:"))
        assert (
            user_idx < catchall_idx
        ), f"user domain DNS rule (idx {user_idx}) must precede catch-all (idx {catchall_idx})"

    def test_country_rules_before_catchall(self):
        """Country rule-set DNS rules must precede the catch-all."""
        cfg = _build(routing_country="ir")
        tags = _dns_tags(cfg)
        country_indices = [i for i, (_, k) in enumerate(tags) if k.startswith("rule_set:")]
        catchall_idx = next(i for i, (_, k) in enumerate(tags) if k.startswith("inbound:"))
        for ci in country_indices:
            assert ci < catchall_idx, f"country DNS rule at idx {ci} must precede catch-all at idx {catchall_idx}"

    def test_country_dns_uses_bootstrap(self):
        """Country rule-set DNS rules must use bootstrap server (tunneled DoH)."""
        cfg = _build(routing_country="ir")
        for r in cfg["dns"]["rules"]:
            if "rule_set" in r:
                assert (
                    r["server"] == "bootstrap"
                ), f"country DNS rule {r['rule_set']} uses {r['server']}, expected bootstrap"

    def test_user_domain_uses_local_dns(self):
        """User direct domains must resolve via local_dns (system/router)."""
        cfg = _build(routing_rules={"direct": ["example.ir"], "proxy": [], "block": []})
        for r in cfg["dns"]["rules"]:
            if r.get("domain_suffix") == ["example.ir"]:
                assert r["server"] == "local_dns"
                return
        pytest.fail("no DNS rule for example.ir")

    def test_catchall_is_last_dns_rule(self):
        """The tun-in -> remote_proxy catch-all must be the very last DNS rule."""
        cfg = _build(
            routing_country="ir",
            routing_rules={"direct": ["ikco.ir"], "proxy": [], "block": []},
        )
        dns_rules = cfg["dns"]["rules"]
        last = dns_rules[-1]
        assert last.get("inbound") == ["tun-in"], f"last DNS rule should be catch-all, got: {last}"

    def test_no_country_no_extra_dns(self):
        """Without country, only user + catch-all DNS rules exist."""
        cfg = _build(
            routing_country="none",
            routing_rules={"direct": ["a.com"], "proxy": [], "block": []},
        )
        assert len(cfg["dns"]["rules"]) == 2  # user + catch-all


# ===========================================================================
# ROUTE RULE ORDERING
# ===========================================================================


class TestRouteRuleOrdering:
    """Route rules must have correct first-match-wins order."""

    def test_sniff_and_resolve_before_domain_rules(self):
        """sniff + resolve must come BEFORE domain_suffix rules so
        Destination.Fqdn is set for domain matching."""
        cfg = _build(routing_rules={"direct": ["ikco.ir"], "proxy": [], "block": []})
        rules = cfg["route"]["rules"]
        actions = [r.get("action") for r in rules]
        sniff_idx = actions.index("sniff")
        resolve_idx = actions.index("resolve")
        first_domain_idx = next(i for i, r in enumerate(rules) if "domain" in r or "domain_suffix" in r)
        assert (
            sniff_idx < resolve_idx < first_domain_idx
        ), f"order must be sniff({sniff_idx}) < resolve({resolve_idx}) < domain({first_domain_idx})"

    def test_resolve_uses_bootstrap(self):
        """resolve action must use bootstrap DNS server."""
        cfg = _build()
        resolves = [r for r in cfg["route"]["rules"] if r.get("action") == "resolve"]
        assert resolves, "no resolve action found"
        assert resolves[0]["server"] == "bootstrap"

    def test_sniff_before_user_domain_rules(self):
        """TLS/HTTP sniff must come BEFORE domain_suffix rules."""
        cfg = _build(routing_rules={"direct": ["ikco.ir"], "proxy": [], "block": []})
        outbounds = _route_outbounds(cfg)
        sniff_idx = next(i for i, o in enumerate(outbounds) if o == "sniff")
        first_domain_idx = next(i for i, r in enumerate(cfg["route"]["rules"]) if "domain" in r or "domain_suffix" in r)
        assert (
            sniff_idx < first_domain_idx
        ), f"sniff at idx {sniff_idx} must precede first domain rule at idx {first_domain_idx}"

    def test_user_proxy_before_country_direct(self):
        """User proxy rules must outrank country-direct (first-match-wins)."""
        cfg = _build(
            routing_country="ir",
            routing_rules={"direct": [], "proxy": ["special-iran.com"], "block": []},
        )
        rules = cfg["route"]["rules"]
        proxy_idx = next(i for i, r in enumerate(rules) if r.get("domain_suffix") == ["special-iran.com"])
        country_idx = next(i for i, r in enumerate(rules) if r.get("outbound") == "direct" and "rule_set" in r)
        assert proxy_idx < country_idx, f"user proxy at {proxy_idx} must precede country direct at {country_idx}"

    def test_port53_sniff_before_hijack_dns(self):
        """Port-53 sniff must precede hijack-dns action."""
        cfg = _build()
        rules = cfg["route"]["rules"]
        sniff53 = next(i for i, r in enumerate(rules) if r.get("action") == "sniff" and r.get("port") == [53])
        hijack = next(i for i, r in enumerate(rules) if r.get("action") == "hijack-dns")
        assert sniff53 < hijack

    def test_no_sniff_override_destination_field(self):
        """sing-box 1.13 rejects sniff_override_destination in route rules."""
        cfg = _build()
        for r in cfg["route"]["rules"]:
            assert "sniff_override_destination" not in r, f"sniff_override_destination rejected by sing-box 1.13: {r}"


# ===========================================================================
# COUNTRY RULE-SETS
# ===========================================================================


class TestCountryRuleSets:
    """Country rules must be present, valid, and use local .srs files."""

    def test_ir_country_has_two_rules(self):
        cfg = _build(routing_country="ir")
        rule_sets = [r for r in cfg["route"]["rules"] if "rule_set" in r]
        assert len(rule_sets) == 2
        tags = [r["rule_set"] for r in rule_sets]
        assert "ir-rules-0" in tags
        assert "ir-rules-1" in tags

    def test_rule_set_type_is_local(self):
        """rule_set entries must be type: local (not remote)."""
        cfg = _build(routing_country="ir")
        for rs in cfg["route"].get("rule_set", []):
            assert rs["type"] == "local", f"rule_set {rs['tag']} is type={rs['type']}"
            assert rs["format"] == "binary"

    def test_rule_set_path_no_dotdot(self):
        """Paths must be normalized - no '..' segments (sing-box rejects them)."""
        cfg = _build(routing_country="ir")
        for rs in cfg["route"].get("rule_set", []):
            path = rs.get("path", "")
            assert ".." not in path, f"rule_set path has '..': {path}"
            assert os.path.isabs(path), f"rule_set path not absolute: {path}"

    def test_rule_set_srs_files_exist(self):
        """Bundled .srs files must exist on disk."""
        cfg = _build(routing_country="ir")
        for rs in cfg["route"].get("rule_set", []):
            path = rs.get("path", "")
            assert os.path.isfile(path), f"rule_set file missing: {path}"

    def test_no_country_no_rules(self):
        cfg = _build(routing_country="none")
        rule_sets = [r for r in cfg["route"]["rules"] if "rule_set" in r]
        assert len(rule_sets) == 0

    def test_country_rules_before_final_proxy(self):
        """Country rules must come before route.final proxy."""
        cfg = _build(routing_country="ir")
        assert cfg["route"]["final"] == "proxy"
        last_rule = cfg["route"]["rules"][-1]
        assert last_rule.get("outbound") == "direct", f"last rule should be country direct, got: {last_rule}"


# ===========================================================================
# ROUTING TOGGLES
# ===========================================================================


class TestRoutingToggles:
    """block_udp_443 and block_ads must reach sing-box config."""

    def test_block_quic(self):
        cfg = _build(toggles={"block_udp_443": True, "block_ads": False})
        quic = [
            r
            for r in cfg["route"]["rules"]
            if r.get("network") == "udp" and r.get("port") == 443 and r.get("outbound") == "block"
        ]
        assert quic, "block_udp_443=True but no udp/443->block rule found"

    def test_block_ads(self):
        cfg = _build(toggles={"block_udp_443": False, "block_ads": True})
        ads = [r for r in cfg["route"]["rules"] if r.get("rule_set") == "ads-rules" and r.get("outbound") == "block"]
        assert ads, "block_ads=True but no ads-rules->block rule found"
        rule_sets = [rs for rs in cfg["route"].get("rule_set", []) if rs["tag"] == "ads-rules"]
        assert rule_sets, "block_ads=True but no ads-rules rule_set defined"

    def test_toggles_off_no_extra_rules(self):
        cfg = _build(toggles={"block_udp_443": False, "block_ads": False})
        block_rules = [r for r in cfg["route"]["rules"] if r.get("outbound") == "block"]
        for r in block_rules:
            assert "rule_set" not in r, f"unexpected ads block rule: {r}"
            assert r.get("port") != 443, f"unexpected QUIC block rule: {r}"


# ===========================================================================
# USER ROUTING RULES
# ===========================================================================


class TestUserRoutingRules:
    """User direct/proxy/block rules appear correctly in config."""

    def test_direct_domains(self):
        cfg = _build(routing_rules={"direct": ["ikco.ir", "bmi.ir"], "proxy": [], "block": []})
        direct_suffixes = []
        for r in cfg["route"]["rules"]:
            if r.get("outbound") == "direct" and "domain_suffix" in r:
                direct_suffixes.extend(r["domain_suffix"])
        assert "ikco.ir" in direct_suffixes
        assert "bmi.ir" in direct_suffixes

    def test_proxy_domains(self):
        cfg = _build(routing_rules={"direct": [], "proxy": ["openai.com"], "block": []})
        proxy_suffixes = []
        for r in cfg["route"]["rules"]:
            if r.get("outbound") == "proxy" and "domain_suffix" in r:
                proxy_suffixes.extend(r["domain_suffix"])
        assert "openai.com" in proxy_suffixes

    def test_block_domains(self):
        cfg = _build(routing_rules={"direct": [], "proxy": [], "block": ["ads.example.com"]})
        block_suffixes = []
        for r in cfg["route"]["rules"]:
            if r.get("outbound") == "block" and "domain_suffix" in r:
                block_suffixes.extend(r["domain_suffix"])
        assert "ads.example.com" in block_suffixes

    def test_direct_ip_cidr(self):
        cfg = _build(routing_rules={"direct": ["10.0.0.5"], "proxy": [], "block": []})
        direct_ips = []
        for r in cfg["route"]["rules"]:
            if r.get("outbound") == "direct" and "ip_cidr" in r:
                ips = r["ip_cidr"]
                if isinstance(ips, str):
                    ips = [ips]
                direct_ips.extend(ips)
        assert "10.0.0.5" in direct_ips


# ===========================================================================
# SING-BOX CONFIG VALIDITY (integration)
# ===========================================================================


class TestSingboxConfigValidity:
    """Generated configs must pass sing-box check."""

    @pytest.fixture()
    def singbox_bin(self):
        """Path to sing-box binary if available."""
        candidate = os.path.join(os.path.dirname(__file__), "..", "bin", "sing-box.exe")
        if os.path.isfile(candidate):
            return candidate
        pytest.skip("sing-box binary not found")

    def test_minimal_config_valid(self, singbox_bin, tmp_path):
        cfg = _build()
        cfg_path = tmp_path / "test.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        result = subprocess.run(
            [singbox_bin, "check", "-c", str(cfg_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"sing-box check failed:\n{result.stderr}"

    def test_country_config_valid(self, singbox_bin, tmp_path):
        cfg = _build(
            routing_country="ir",
            routing_rules={"direct": ["ikco.ir"], "proxy": ["openai.com"], "block": []},
            toggles={"block_udp_443": True, "block_ads": True},
        )
        cfg_path = tmp_path / "test_ir.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        result = subprocess.run(
            [singbox_bin, "check", "-c", str(cfg_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"sing-box check failed:\n{result.stderr}"
