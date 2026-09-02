"""Sing-box User routing rules and toggles injector."""

from __future__ import annotations

from typing import Dict, List, Optional

from src.utils.network_utils import NetworkUtils


class UserRulesInjector:
    """Parses and injects user routing rules and quick toggles into sing-box config."""

    def inject(
        self,
        rules: list,
        dns_rules: list,
        routing_rules: Optional[Dict],
        toggles: Optional[Dict] = None,
        insert_index: int = -1,
        cfg_route: Optional[dict] = None,
    ) -> None:
        """Inject user-defined direct/proxy/block rules and quick-toggles in-place.

        Args:
            rules: Target sing-box route rules list.
            dns_rules: Target sing-box dns rules list.
            routing_rules: User rules dict ``{"direct": [...], "proxy": [...], "block": [...]}``.
            toggles: Quick-toggles dict ``{"block_udp_443": bool, "block_ads": bool}``.
            insert_index: Index in ``rules`` to insert user rules at (before sniff/hijack-dns).
            cfg_route: Optional sing-box route block dict (for adding rule_set configs).
        """
        if not routing_rules and not toggles:
            return

        new_rules: List[dict] = []
        new_dns_rules: List[dict] = []

        if routing_rules:
            for action in ("direct", "proxy", "block"):
                targets = routing_rules.get(action, [])
                if not targets:
                    continue

                s_ips: List[str] = []
                s_domains: List[str] = []
                s_domain_suffixes: List[str] = []

                for t in targets:
                    t = t.strip()
                    if not t:
                        continue

                    if NetworkUtils.is_valid_ip_cidr(t):
                        s_ips.append(t)
                        continue

                    lower_t = t.lower()
                    # Xray geosite:/geoip: tags are incompatible with sing-box loose
                    # config (require .db or rule_set downloads) — skip silently.
                    if lower_t.startswith("geosite:") or lower_t.startswith("geoip:"):
                        continue

                    if lower_t.startswith("domain:"):
                        s_domain_suffixes.append(t[7:])
                    elif lower_t.startswith("full:"):
                        s_domains.append(t[5:])
                    else:
                        # Bare hostname → treat as domain suffix
                        s_domain_suffixes.append(t)

                if s_ips:
                    new_rules.append({"ip_cidr": s_ips, "outbound": action})

                if s_domains:
                    new_rules.append({"domain": s_domains, "outbound": action})
                    if action == "direct":
                        new_dns_rules.append({"domain": s_domains, "server": "local_dns"})
                    elif action == "block":
                        new_dns_rules.append({"domain": s_domains, "action": "reject"})

                if s_domain_suffixes:
                    new_rules.append({"domain_suffix": s_domain_suffixes, "outbound": action})
                    if action == "direct":
                        new_dns_rules.append({"domain_suffix": s_domain_suffixes, "server": "local_dns"})
                    elif action == "block":
                        new_dns_rules.append({"domain_suffix": s_domain_suffixes, "action": "reject"})

        # Routing quick-toggles: block QUIC (udp/443) and ad domains.
        if toggles:
            toggle_rules: List[dict] = []
            if toggles.get("block_udp_443", False):
                toggle_rules.append({"network": "udp", "port": 443, "outbound": "block"})
            if toggles.get("block_ads", False):
                if cfg_route is not None:
                    from src.core.singbox.builders.rule_set_utils import (
                        materialize_rule_set,
                    )

                    ads_url = (
                        "https://raw.githubusercontent.com/Chocolate4U/"
                        "Iran-sing-box-rules/rule-set/geosite-category-ads-all.srs"
                    )
                    # Offline-first: cached on disk -> local; missing -> rule dropped
                    # entirely (never a remote @url fetch that FATALs with EOF).
                    rule_set = materialize_rule_set(
                        "ads-rules", ads_url, download_detour="proxy"
                    )
                    if rule_set is not None:
                        toggle_rules.append({"rule_set": "ads-rules", "outbound": "block"})
                        new_dns_rules.append({"rule_set": "ads-rules", "action": "reject"})
                        cfg_route.setdefault("rule_set", []).append(rule_set)
            new_rules.extend(toggle_rules)

        # Insert BEFORE the default chain (hijack-dns / block / private-direct).
        if insert_index < 0:
            insert_index = len(rules)
        for i, r in enumerate(new_rules):
            rules.insert(insert_index + i, r)
        dns_rules.extend(new_dns_rules)
