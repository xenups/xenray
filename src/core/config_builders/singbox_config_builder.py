"""Sing-box JSON configuration builder.

Pure, side-effect-free facade/director for generating sing-box JSON configuration.
Coordinates specialized builders for DNS, inbounds/outbounds, routing loop-breakers,
user routing rules, and country-based rule sets in dual-engine TUN mode (Xray + sing-box).

Design rules:
- No subprocess calls.
- No OS or registry state mutations.
- No I/O of any kind.
- Fully deterministic given the same inputs → easy to unit-test.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from src.core.logger import logger
from src.core.singbox.builders.country_rules_injector import CountryRulesInjector
from src.core.singbox.builders.dns_config_builder import DnsConfigBuilder
from src.core.singbox.builders.route_config_builder import RouteConfigBuilder
from src.core.singbox.builders.user_rules_injector import UserRulesInjector
from src.utils.network_utils import NetworkUtils


class SingboxConfigBuilder:
    """Builds the sing-box JSON configuration dict via specialized builders.

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

    def __init__(
        self,
        dns_builder: Optional[DnsConfigBuilder] = None,
        route_builder: Optional[RouteConfigBuilder] = None,
        user_rules_injector: Optional[UserRulesInjector] = None,
        country_rules_injector: Optional[CountryRulesInjector] = None,
    ):
        self._dns_builder = dns_builder or DnsConfigBuilder()
        self._route_builder = route_builder or RouteConfigBuilder()
        self._user_rules_injector = user_rules_injector or UserRulesInjector()
        self._country_rules_injector = country_rules_injector or CountryRulesInjector()

    @property
    def dns_builder(self) -> DnsConfigBuilder:
        if not hasattr(self, "_dns_builder") or self._dns_builder is None:
            self._dns_builder = DnsConfigBuilder()
        return self._dns_builder

    @property
    def route_builder(self) -> RouteConfigBuilder:
        if not hasattr(self, "_route_builder") or self._route_builder is None:
            self._route_builder = RouteConfigBuilder()
        return self._route_builder

    @property
    def user_rules_injector(self) -> UserRulesInjector:
        if not hasattr(self, "_user_rules_injector") or self._user_rules_injector is None:
            self._user_rules_injector = UserRulesInjector()
        return self._user_rules_injector

    @property
    def country_rules_injector(self) -> CountryRulesInjector:
        if not hasattr(self, "_country_rules_injector") or self._country_rules_injector is None:
            self._country_rules_injector = CountryRulesInjector()
        return self._country_rules_injector

    # ------------------------------------------------------------------
    # Static helpers (delegated to NetworkUtils for SRP & backward compatibility)
    # ------------------------------------------------------------------

    normalize_list = staticmethod(NetworkUtils.normalize_list)
    filter_real_ips = staticmethod(NetworkUtils.filter_real_ips)
    filter_domains = staticmethod(NetworkUtils.filter_domains)
    _is_valid_ip_cidr = staticmethod(NetworkUtils.is_valid_ip_cidr)
    _is_ipv4 = staticmethod(NetworkUtils.is_ipv4)

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
        local_dns_server: Optional[str] = None,
        bypass_process_names: Optional[List[str]] = None,
        sni_connect_ip: Optional[str] = None,
        toggles: Optional[Dict] = None,
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
            local_dns_server: Injected local DNS server IP for direct domains.
            bypass_process_names: Injected list of process names to bypass.
            sni_connect_ip: Injected SNI spoof target IP/domain to bypass.
            toggles: Routing quick-toggles ``{"block_udp_443": bool,
                "block_ads": bool}`` from the routing page.

        Returns:
            Complete sing-box configuration as a Python dict ready to be
            serialised with ``json.dump``.
        """
        proxy_list = self.normalize_list(proxy_server_ip)
        proxy_ips = self.filter_real_ips(proxy_list)
        proxy_domains = self.filter_domains(proxy_list)

        cfg: dict = {
            "log": {"level": "warn", "timestamp": True},
            "dns": self.dns_builder.build(local_dns_server=local_dns_server),
            "inbounds": self.route_builder.build_inbounds(mtu=mtu),
            "outbounds": self.route_builder.build_outbounds(
                socks_port=socks_port,
                interface_name=interface_name,
            ),
            "route": self.route_builder.build_base_route(
                interface_name=interface_name,
                bypass_process_names=bypass_process_names,
            ),
        }

        rules = cfg["route"]["rules"]
        dns_rules = cfg["dns"]["rules"]

        # --- Proxy server IP / domain bypass rules & SNI loop-breakers ---
        insert_index = self.route_builder.inject_loop_breakers(
            rules=rules,
            dns_rules=dns_rules,
            proxy_ips=proxy_ips,
            proxy_domains=proxy_domains,
            sni_connect_ip=sni_connect_ip,
        )

        # --- User routing rules (direct / proxy / block) ---
        # sniff → resolve → domain rules:
        # 1. sniff extracts SNI/Host into metadata.SniffedHostname
        # 2. resolve looks up the domain via bootstrap DNS and sets
        #    metadata.Destination.Fqdn — which is what domain_suffix
        #    and rule_set domain items actually match against.
        rules.insert(insert_index, {"inbound": ["tun-in"], "action": "sniff"})
        insert_index += 1
        rules.insert(insert_index, {"inbound": ["tun-in"], "action": "resolve", "server": "bootstrap"})
        insert_index += 1

        self.user_rules_injector.inject(
            rules=rules,
            dns_rules=dns_rules,
            routing_rules=routing_rules,
            toggles=toggles,
            insert_index=insert_index,
            cfg_route=cfg["route"],
        )

        # --- Country rule sets ---
        # Country DNS rules must come BEFORE the catch-all so geosite:ir
        # domains resolve via bootstrap, not remote_proxy.
        self.country_rules_injector.inject(
            cfg_route=cfg["route"],
            dns_rules=dns_rules,
            routing_country=routing_country,
        )

        # Catch-all DNS rule AFTER all specific rules (user + country)
        # so first-match-wins routes ikco.ir → local_dns, ir domains →
        # bootstrap, everything else → remote_proxy.
        cfg["dns"]["rules"].append({"inbound": ["tun-in"], "server": "remote_proxy"})

        # --- Outbounds & DNS Integrity Validation for sing-box 1.14.0 ---
        outbounds = cfg.setdefault("outbounds", [])
        existing_tags = {o.get("tag") for o in outbounds if isinstance(o, dict)}

        if "direct" not in existing_tags:
            outbounds.append({"type": "direct", "tag": "direct"})

        if "block" not in existing_tags:
            outbounds.append({"type": "block", "tag": "block"})

        # Reconcile DNS servers against sing-box 1.14.0 rules
        for s in cfg.get("dns", {}).get("servers", []):
            tag = s.get("tag")
            if tag == "local_dns":
                # For default/local DNS, ensure native sing-box 1.13+ local resolver syntax without detour
                if s.get("address") == "local" or s.get("server") == "local" or s.get("type") == "local":
                    s["type"] = "local"
                    s.pop("address", None)
                    s.pop("server", None)
                    s.pop("detour", None)
                elif s.get("type") == "udp":
                    # For explicit IP local DNS, omit detour to empty direct so it routes dynamically
                    s.pop("detour", None)
            elif tag in ("remote_proxy", "bootstrap"):
                if "proxy" in existing_tags:
                    s["detour"] = "proxy"

        logger.debug(f"[SingboxConfigBuilder] Total route rules: {len(rules)}")
        logger.debug(f"[SingboxConfigBuilder] Total DNS rules:   {len(dns_rules)}")
        for idx, rule in enumerate(rules[:10]):
            logger.debug(f"[SingboxConfigBuilder] Route rule {idx}: {rule}")

        return cfg

    def _apply_user_routing_rules(
        self,
        cfg: dict,
        routing_rules: Optional[Dict],
        insert_at: int = -1,
        toggles: Optional[Dict] = None,
    ) -> None:
        """Backward-compatibility helper delegating to UserRulesInjector."""
        self.user_rules_injector.inject(
            rules=cfg["route"]["rules"],
            dns_rules=cfg["dns"]["rules"],
            routing_rules=routing_rules,
            toggles=toggles,
            insert_index=insert_at,
            cfg_route=cfg["route"],
        )

    def _apply_country_rules(self, cfg: dict, routing_country: str) -> None:
        """Backward-compatibility helper delegating to CountryRulesInjector."""
        self.country_rules_injector.inject(
            cfg_route=cfg["route"],
            dns_rules=cfg["dns"]["rules"],
            routing_country=routing_country,
        )
