"""TUN inbound injection for Xray VPN mode."""

import ipaddress
from typing import Optional

from loguru import logger

from src.core.app_context import AppContext
from src.core.constants import (
    DNS_IP_CLOUDFLARE,
    DNS_IP_GOOGLE,
    DOMAIN_ASIS,
    GEOIP_PREFIX,
    GEOSITE_PREFIX,
    NCSI_BYPASS_DOMAINS,
    PROTOCOL_TUN,
    RULE_FIELD,
    TAG_BLOCK,
    TAG_DIRECT,
    TAG_PROXY,
    TUN_GATEWAY_IPV4,
    TUN_ROUTE_IPV4,
    XRAY_COUNTRY_GEOIP,
)
from src.services.connection.dns_configurator import DnsConfigurator


def _is_ip(address: str) -> bool:
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False


is_ip = _is_ip


class TunInjector:
    """Injects TUN inbound and routing rules for VPN mode."""

    def __init__(self, app_context: AppContext):
        self._app_context = app_context

    def inject(
        self,
        config: dict,
        dns_servers: list,
        mtu: int = 1500,
        routing_country: str = "",
        routing_rules: Optional[dict] = None,
        proxy_server_ips: Optional[list] = None,
    ):
        """Inject TUN inbound and routing rules into config."""
        if routing_rules is None:
            routing_rules = {TAG_DIRECT: [], TAG_PROXY: [], TAG_BLOCK: []}
        if proxy_server_ips is None:
            proxy_server_ips = []

        tun_inbound = {
            "tag": PROTOCOL_TUN,
            "protocol": PROTOCOL_TUN,
            "settings": {
                "name": "xenray-tun",
                "mtu": mtu,
                # IPv4-only subnet — IPv6 is disabled on the TUN to avoid
                # system-stack prefix binding errors and IPv6 latency spikes.
                "gateway": [TUN_GATEWAY_IPV4],
                "dns": dns_servers,
                # Capture the IPv4 default route only (IPv6 disabled).
                "autoSystemRoutingTable": [TUN_ROUTE_IPV4],
            },
            "sniffing": {
                "enabled": True,
                "destOverride": ["fakedns", "http", "tls", "quic"],
                "metadataOnly": False,
                "routeOnly": False,
            },
        }

        if "inbounds" not in config:
            config["inbounds"] = []
        config["inbounds"] = [ib for ib in config["inbounds"] if ib.get("protocol") != PROTOCOL_TUN]
        config["inbounds"].insert(0, tun_inbound)
        logger.info(f"[TunInjector] Injected TUN inbound (MTU={mtu})")

        # Ensure dns-out outbound exists so Xray's DNS engine can process port 53 traffic
        outbounds = config.setdefault("outbounds", [])
        if not any(ob.get("protocol") == "dns" for ob in outbounds):
            outbounds.append({"protocol": "dns", "tag": "dns-out"})
            logger.info("[TunInjector] Injected dns-out outbound")

        # Extract remote DNS targets and direct/bootstrap DNS targets from config["dns"]["servers"]
        remote_dns_targets = []
        direct_dns_targets = []

        dns_servers_list = config.get("dns", {}).get("servers", [])
        for s in dns_servers_list:
            if isinstance(s, dict):
                addr = s.get("address", "")
                detour = s.get("detour", "")
            else:
                addr = s
                detour = ""

            # Use the shared helper which correctly handles IPv6 addresses
            # (bare multi-colon addresses are not split on ':'), DoH/DoT/DoQ
            # scheme prefixes, and URL paths.
            cleaned = DnsConfigurator._to_bare_address(addr)

            if detour == TAG_DIRECT:
                direct_dns_targets.append(cleaned)
            elif detour == TAG_PROXY:
                remote_dns_targets.append(cleaned)
            else:
                # Default fallback: known public DNS resolvers are treated as direct
                if cleaned in (DNS_IP_CLOUDFLARE, DNS_IP_GOOGLE):
                    direct_dns_targets.append(cleaned)

        routing_section = config.setdefault("routing", {})
        # AsIs: pass destination domains to the routing engine WITHOUT resolving
        # them client-side. This lets the egress server resolve raw domains with
        # its own system DNS (server-side resolution). No extra client DNS work
        # is done for routing decisions.
        routing_section["domainStrategy"] = DOMAIN_ASIS
        existing_rules: list = routing_section.setdefault("rules", [])

        new_rules = self._build_routing_rules(
            routing_country=routing_country,
            routing_rules=routing_rules,
            proxy_server_ips=proxy_server_ips,
            remote_dns_targets=remote_dns_targets,
            direct_dns_targets=direct_dns_targets,
        )

        routing_section["rules"] = new_rules + existing_rules
        logger.info(
            f"[TunInjector] Injected {len(new_rules)} TUN routing rules" f" (country={routing_country or 'none'})"
        )

    def _build_routing_rules(
        self,
        routing_country: str,
        routing_rules: dict,
        proxy_server_ips: list,
        remote_dns_targets: list = None,
        direct_dns_targets: list = None,
    ) -> list:
        """Build Xray routing rules for TUN/VPN mode."""
        if remote_dns_targets is None:
            remote_dns_targets = []
        if direct_dns_targets is None:
            direct_dns_targets = []

        toggles = self._app_context.routing.load_toggles()
        rules: list = []

        # 0. SNI Spoof: CONNECT_IP -> direct (loop-breaker).
        # When SNI spoofing is enabled, the spoof helper's upstream socket to
        # CONNECT_IP must go DIRECT out the physical NIC — never re-enter the
        # TUN route (default route) — or it loops. Placed FIRST so first-match
        # wins over the TUN capture rules below.
        try:
            if self._app_context.settings.get_sni_spoof_enabled():
                connect_ip = self._app_context.settings.get_sni_connect_ip()
                if connect_ip:
                    rules.append({"type": RULE_FIELD, "ip": [connect_ip], "outboundTag": TAG_DIRECT})
        except Exception:
            pass

        # 1. Port 53 -> dns-out. Scoped to the TUN inbound ONLY so Xray's own
        #    internal DNS client queries (to remote/direct DNS servers via their
        #    detours) are NOT re-captured — this prevents the recursion loop where
        #    internal udp:X.X.X.X:53 queries got re-routed back into dns-out.
        rules.append(
            {
                "type": RULE_FIELD,
                "inboundTag": [PROTOCOL_TUN],
                "port": "53",
                "outboundTag": "dns-out",
            }
        )

        # 2. Remote DNS IP/Server -> proxy
        remote_ips = [t for t in remote_dns_targets if is_ip(t)]
        remote_domains = [t for t in remote_dns_targets if not is_ip(t)]
        if remote_ips:
            rules.append({"type": RULE_FIELD, "ip": remote_ips, "outboundTag": TAG_PROXY})
        if remote_domains:
            rules.append({"type": RULE_FIELD, "domain": remote_domains, "outboundTag": TAG_PROXY})

        # 3. Direct/Bootstrap DNS IPs -> direct
        direct_ips = [t for t in direct_dns_targets if is_ip(t)]
        direct_domains = [t for t in direct_dns_targets if not is_ip(t)]
        if direct_ips:
            rules.append({"type": RULE_FIELD, "ip": direct_ips, "outboundTag": TAG_DIRECT})
        if direct_domains:
            rules.append(
                {
                    "type": RULE_FIELD,
                    "domain": direct_domains,
                    "outboundTag": TAG_DIRECT,
                }
            )

        # 4. NCSI probe domains -> direct (without external geosite dependency)
        rules.append(
            {
                "type": RULE_FIELD,
                "domain": list(NCSI_BYPASS_DOMAINS),
                "outboundTag": TAG_DIRECT,
            }
        )

        if proxy_server_ips:
            ips = [addr for addr in proxy_server_ips if is_ip(addr)]
            domains = [addr for addr in proxy_server_ips if not is_ip(addr)]

            if ips:
                rules.append({"type": RULE_FIELD, "ip": ips, "outboundTag": TAG_DIRECT})
            if domains:
                rules.append({"type": RULE_FIELD, "domain": domains, "outboundTag": TAG_DIRECT})

        user_block = routing_rules.get(TAG_BLOCK, [])
        if user_block:
            block_ips = [t for t in user_block if is_ip(t)]
            block_domains = [t for t in user_block if not is_ip(t)]
            if block_ips:
                rules.append({"type": RULE_FIELD, "ip": block_ips, "outboundTag": TAG_BLOCK})
            if block_domains:
                rules.append({"type": RULE_FIELD, "domain": block_domains, "outboundTag": TAG_BLOCK})

        if toggles.get("block_udp_443", False):
            rules.append(
                {
                    "type": RULE_FIELD,
                    "network": "udp",
                    "port": "443",
                    "outboundTag": TAG_BLOCK,
                }
            )

        if toggles.get("block_ads", False):
            rules.append(
                {
                    "type": RULE_FIELD,
                    "domain": [GEOSITE_PREFIX + "category-ads-all"],
                    "outboundTag": TAG_BLOCK,
                }
            )

        user_direct = routing_rules.get(TAG_DIRECT, [])
        if user_direct:
            direct_ips = [t for t in user_direct if is_ip(t)]
            direct_domains = [t for t in user_direct if not is_ip(t)]
            if direct_ips:
                rules.append({"type": RULE_FIELD, "ip": direct_ips, "outboundTag": TAG_DIRECT})
            if direct_domains:
                rules.append({"type": RULE_FIELD, "domain": direct_domains, "outboundTag": TAG_DIRECT})

        if toggles.get("direct_private_ips", True):
            rules.append(
                {
                    "type": RULE_FIELD,
                    "ip": [GEOIP_PREFIX + "private"],
                    "outboundTag": TAG_DIRECT,
                }
            )

        country = (routing_country or "").lower().strip()
        geoip_tags = XRAY_COUNTRY_GEOIP.get(country, [])
        if geoip_tags:
            rules.append({"type": RULE_FIELD, "ip": geoip_tags, "outboundTag": TAG_DIRECT})
            rules.append(
                {
                    "type": RULE_FIELD,
                    "domain": [f"{GEOSITE_PREFIX}{country}"],
                    "outboundTag": TAG_DIRECT,
                }
            )

        user_proxy = routing_rules.get(TAG_PROXY, [])
        if user_proxy:
            proxy_ips = [t for t in user_proxy if is_ip(t)]
            proxy_domains = [t for t in user_proxy if not is_ip(t)]
            if proxy_ips:
                rules.append({"type": RULE_FIELD, "ip": proxy_ips, "outboundTag": TAG_PROXY})
            if proxy_domains:
                rules.append({"type": RULE_FIELD, "domain": proxy_domains, "outboundTag": TAG_PROXY})

        return rules
