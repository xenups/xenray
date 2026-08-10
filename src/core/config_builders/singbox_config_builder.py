"""Sing-box JSON configuration builder.

Pure, side-effect-free builder extracted from ``SingboxService``.
Constructs the full sing-box JSON configuration dict for the dual-engine
TUN mode (Xray as SOCKS proxy, sing-box as TUN engine).

Design rules:
- No subprocess calls.
- No OS or registry state mutations.
- No I/O of any kind.
- Fully deterministic given the same inputs → easy to unit-test.
"""

from __future__ import annotations

import ipaddress
import os
import sys
from typing import Dict, List, Optional, Union

from src.core.constants import (
    DNS_IP_GOOGLE,
    DNS_IP_CLOUDFLARE,
    SINGBOX_RULE_SETS,
    TUN_GATEWAY_IPV4,
    XRAY_EXECUTABLE,
    BASE_BYPASS_PROCESSES,
)
from src.core.logger import logger
from src.utils.platform_utils import PlatformUtils


class SingboxConfigBuilder:
    """Builds the sing-box JSON configuration dict.

    Usage::

        builder = SingboxConfigBuilder()
        cfg = builder.build(
            socks_port=10805,
            proxy_server_ip="my.proxy.example.com",
            routing_country="ir",
            interface_name="Wi-Fi",
            routing_rules={"direct": ["192.168.1.0/24"]},
            mtu=1420,
        )
    """

    # ------------------------------------------------------------------
    # Static helpers (ported verbatim from SingboxService)
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_list(value: Union[str, List[str], None]) -> List[str]:
        """Normalize input to a cleaned list of lowercase strings."""
        if not value:
            return []
        if isinstance(value, str):
            value = [value]
        return [
            item.strip().lower().replace("'", "").replace('"', "").replace("[", "").replace("]", "")
            for item in value
            if isinstance(item, str)
        ]

    @staticmethod
    def filter_real_ips(lst: List[str]) -> List[str]:
        """Return only the entries that are valid IP addresses."""
        result = []
        for item in lst:
            try:
                ipaddress.ip_address(item)
                result.append(item)
            except (ValueError, ipaddress.AddressValueError):
                continue
        return result

    @staticmethod
    def filter_domains(lst: List[str]) -> List[str]:
        """Return only the entries that are domain names (not IPs)."""
        valid_ips: set = set(SingboxConfigBuilder.filter_real_ips(lst))
        return [item for item in lst if item not in valid_ips]

    # ------------------------------------------------------------------
    # Main build method
    # ------------------------------------------------------------------

    def build(
        self,
        socks_port: int,
        proxy_server_ip: Union[str, List[str]],
        routing_country: str = "",
        interface_name: Optional[str] = None,
        routing_rules: Optional[Dict] = None,
        mtu: int = 1420,
    ) -> dict:
        """Generate the full sing-box JSON configuration dict.

        Args:
            socks_port: Xray SOCKS5 port that sing-box routes tunnel traffic into.
            proxy_server_ip: Proxy server hostname(s)/IP(s) to bypass via direct
                outbound inside the sing-box rule set (Wintun loop break).
            routing_country: ISO country code for country-based rule sets
                (``""`` / ``"none"`` to disable).
            interface_name: Physical network interface name to bind the ``direct``
                outbound and ``default_interface`` to.
            routing_rules: User-supplied routing overrides:
                ``{"direct": [...], "proxy": [...], "block": [...]}``.
            mtu: TUN adapter MTU (default 1420).

        Returns:
            Complete sing-box configuration as a Python dict ready to be
            serialised with ``json.dump``.
        """
        proxy_list = self.normalize_list(proxy_server_ip)
        proxy_ips = self.filter_real_ips(proxy_list)
        proxy_domains = self.filter_domains(proxy_list)

        # Build process bypass list — include the frozen binary if running packed.
        current_exe = os.path.basename(sys.executable).lower()
        is_windows = PlatformUtils.get_platform() == "windows"
        process_names = [f"{proc}.exe" if is_windows else proc for proc in BASE_BYPASS_PROCESSES]
        if current_exe not in process_names:
            process_names.append(current_exe)

        cfg: dict = {
            "log": {"level": "warn", "timestamp": True},
            "dns": {
                "servers": [
                    {
                        "tag": "bootstrap",
                        "type": "udp",
                        # Google DNS as bootstrap — referenced by constant so tests can
                        # assert the value without embedding a literal string.
                        "server": DNS_IP_GOOGLE,
                        "detour": "direct",
                    },
                    {
                        "tag": "remote_proxy",
                        # DoH through the SOCKS proxy avoids port-53 blocking and
                        # UDP ASSOCIATE limitations in Xray's SOCKS inbound.
                        # sing-box appends /dns-query automatically for type="https".
                        "type": "https",
                        "server": DNS_IP_CLOUDFLARE,
                        "domain_resolver": "bootstrap",
                        "detour": "proxy",
                    },
                ],
                "rules": [
                    {
                        "inbound": ["tun-in"],
                        "server": "remote_proxy",
                    },
                ],
                "final": "remote_proxy",
                # IPv4-only: never query AAAA to avoid IPv6 stack errors and
                # latency spikes while IPv6 is disabled on the TUN adapter.
                "strategy": "ipv4_only",
                "disable_cache": False,
                "disable_expire": False,
                "independent_cache": True,
            },
            "inbounds": [
                {
                    "type": "tun",
                    "tag": "tun-in",
                    "interface_name": PlatformUtils.get_tun_interface_name(),
                    # IPv4-only subnet — single address avoids IPv6 prefix binding
                    # errors ("need one more IPv6 address...").
                    "address": [TUN_GATEWAY_IPV4],
                    "mtu": mtu,
                    "auto_route": True,
                    "strict_route": True,
                    "stack": "mixed",
                    # sniff/sniff_override_destination moved to route.rules
                    # (sing-box 1.11.0+: inbound sniff fields removed).
                    "endpoint_independent_nat": True,
                }
            ],
            "outbounds": [
                {
                    "type": "socks",
                    "tag": "proxy",
                    "server": "127.0.0.1",
                    "server_port": socks_port,
                    "domain_resolver": "remote_proxy",
                },
                {
                    "type": "direct",
                    "tag": "direct",
                    "domain_resolver": "bootstrap",
                    **({"bind_interface": interface_name} if interface_name else {}),
                },
                {"type": "block", "tag": "block"},
            ],
            "route": {
                "rules": [
                    # Process bypass FIRST — Python/curl/xray subprocess traffic
                    # bypasses TUN on Windows before any IP/domain rules fire.
                    {
                        "process_name": process_names,
                        "outbound": "direct",
                    },
                    {"process_path": [XRAY_EXECUTABLE], "outbound": "direct"},
                    # Port-53 sniff so the DNS protocol can be detected for hijack.
                    # Scoped to port 53 only to minimise per-packet overhead.
                    {
                        "inbound": ["tun-in"],
                        "port": [53],
                        "action": "sniff",
                    },
                    {
                        "protocol": "dns",
                        "action": "hijack-dns",
                    },
                    {"network": "udp", "port": 443, "outbound": "proxy"},
                    {"ip_cidr": ["224.0.0.0/3", "ff00::/8"], "outbound": "block"},
                    {
                        "ip_cidr": [
                            "10.0.0.0/8",
                            "172.16.0.0/12",
                            "192.168.0.0/16",
                            "127.0.0.0/8",
                            "169.254.0.0/16",
                            "fc00::/7",  # IPv6 ULA
                            "fe80::/10",  # IPv6 Link-Local
                            "::1/128",  # IPv6 loopback
                        ],
                        "outbound": "direct",
                    },
                ],
                "final": "proxy",
                "auto_detect_interface": True,
                **({"default_interface": interface_name} if interface_name else {}),
            },
        }

        rules = cfg["route"]["rules"]
        dns_rules = cfg["dns"]["rules"]

        # --- Proxy server IP / domain bypass rules ---
        # NOTE: Public DNS resolvers (1.1.1.1, 8.8.8.8) are deliberately NOT
        # routed 'direct' here.  All port-53 / DNS traffic is captured by the
        # sniff+hijack-dns rule chain above.  A 'direct' rule for a public DNS
        # IP would bypass the hijack and re-enable ISP-level DNS tampering.
        insert_index = len([r for r in rules if "process" in r])

        for ip in proxy_ips:
            rules.insert(insert_index, {"ip_cidr": f"{ip}/32", "outbound": "direct"})
            insert_index += 1

        for domain in proxy_domains:
            rules.insert(insert_index, {"domain_suffix": domain, "outbound": "direct"})
            insert_index += 1
            dns_rules.append({"domain_suffix": domain, "server": "bootstrap"})

        # --- User routing rules (direct / proxy / block) ---
        self._apply_user_routing_rules(cfg, routing_rules)

        # --- Country rule sets ---
        self._apply_country_rules(cfg, routing_country)

        logger.debug(f"[SingboxConfigBuilder] Total route rules: {len(rules)}")
        logger.debug(f"[SingboxConfigBuilder] Total DNS rules:   {len(dns_rules)}")
        for idx, rule in enumerate(rules[:10]):
            logger.debug(f"[SingboxConfigBuilder] Route rule {idx}: {rule}")

        return cfg

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_valid_ip_cidr(val: str) -> bool:
        try:
            ipaddress.ip_network(val, strict=False)
            return True
        except ValueError:
            return False

    def _apply_user_routing_rules(self, cfg: dict, routing_rules: Optional[Dict]) -> None:
        """Inject user-defined direct/proxy/block rules into cfg in-place."""
        if not routing_rules:
            return

        rules = cfg["route"]["rules"]
        dns_rules = cfg["dns"]["rules"]

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

                if self._is_valid_ip_cidr(t):
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
                rules.append({"ip_cidr": s_ips, "outbound": action})

            if s_domains:
                rules.append({"domain": s_domains, "outbound": action})
                if action == "direct":
                    dns_rules.append({"domain": s_domains, "server": "bootstrap"})

            if s_domain_suffixes:
                rules.append({"domain_suffix": s_domain_suffixes, "outbound": action})
                if action == "direct":
                    dns_rules.append({"domain_suffix": s_domain_suffixes, "server": "bootstrap"})

    def _apply_country_rules(self, cfg: dict, routing_country: str) -> None:
        """Inject remote rule-set entries for country-based routing."""
        if not routing_country or routing_country.lower() == "none":
            return

        country = routing_country.lower()
        rule_sets_mapping = SINGBOX_RULE_SETS

        if country not in rule_sets_mapping:
            logger.warning(f"[SingboxConfigBuilder] Unknown country code '{country}'")
            return

        logger.info(f"[SingboxConfigBuilder] Applying country routing: {country}")

        if "rule_set" not in cfg["route"]:
            cfg["route"]["rule_set"] = []

        for idx, url in enumerate(rule_sets_mapping[country]):
            tag_name = f"{country}-rules-{idx}"
            logger.debug(f"[SingboxConfigBuilder] Adding rule set: {tag_name} from {url}")

            cfg["route"]["rule_set"].append(
                {
                    "tag": tag_name,
                    "type": "remote",
                    "format": "binary",
                    "url": url,
                    "download_detour": "direct",
                    "update_interval": "24h",
                }
            )
            cfg["route"]["rules"].append({"rule_set": tag_name, "outbound": "direct"})
            cfg["dns"]["rules"].append({"rule_set": tag_name, "server": "bootstrap"})
            logger.info(f"[SingboxConfigBuilder] Country rule added: {tag_name} → direct")
