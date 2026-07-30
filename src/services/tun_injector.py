"""TUN inbound injection for Xray VPN mode."""

from typing import Optional

from loguru import logger

from src.core.app_context import AppContext
from src.core.constants import (
    DOMAIN_IP_IF_NON_MATCH,
    GEOIP_PREFIX,
    GEOSITE_PREFIX,
    PROTOCOL_TUN,
    RULE_FIELD,
    SNIFF_DEST_OVERRIDE,
    TAG_BLOCK,
    TAG_DIRECT,
    TAG_PROXY,
    XRAY_COUNTRY_GEOIP,
)
from src.services.config_utils import is_ip


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
        interface_name: Optional[str] = None,
    ):
        """Inject TUN inbound and routing rules into config."""
        if routing_rules is None:
            routing_rules = {TAG_DIRECT: [], TAG_PROXY: [], TAG_BLOCK: []}
        if proxy_server_ips is None:
            proxy_server_ips = []

        self.patch_all_outbounds_interface(config, interface_name)

        tun_inbound = {
            "tag": PROTOCOL_TUN,
            "protocol": PROTOCOL_TUN,
            "settings": {
                "name": "xenray-tun",
                "mtu": mtu,
                "gateway": ["10.0.0.1/16"],
                "dns": dns_servers,
                "autoSystemRoutingTable": ["0.0.0.0/0", "::/0"],
            },
            "sniffing": {
                "enabled": True,
                "destOverride": list(SNIFF_DEST_OVERRIDE),
                "metadataOnly": False,
                "routeOnly": False,
            },
        }

        if "inbounds" not in config:
            config["inbounds"] = []
        config["inbounds"] = [
            ib for ib in config["inbounds"] if ib.get("protocol") != PROTOCOL_TUN
        ]
        config["inbounds"].insert(0, tun_inbound)
        logger.info(f"[TunInjector] Injected TUN inbound (MTU={mtu})")

        routing_section = config.setdefault("routing", {})
        routing_section["domainStrategy"] = DOMAIN_IP_IF_NON_MATCH
        existing_rules: list = routing_section.setdefault("rules", [])

        new_rules = self._build_routing_rules(
            routing_country=routing_country,
            routing_rules=routing_rules,
            proxy_server_ips=proxy_server_ips,
        )

        routing_section["rules"] = new_rules + existing_rules
        logger.info(
            f"[TunInjector] Injected {len(new_rules)} TUN routing rules"
            f" (country={routing_country or 'none'})"
        )

    def patch_all_outbounds_interface(
        self, config: dict, interface_name: Optional[str]
    ) -> None:
        """Bind ALL outbounds (proxy and freedom) to the physical NIC via sockopt to prevent TUN loops."""
        if not interface_name:
            return
        patched = 0
        for outbound in config.get("outbounds", []):
            stream = outbound.setdefault("streamSettings", {})
            sockopt = stream.setdefault("sockopt", {})
            sockopt["interface"] = interface_name
            patched += 1
        logger.info(
            f"[TunInjector] Bound {patched} outbound(s) to physical interface '{interface_name}'"
        )

    def _build_routing_rules(
        self,
        routing_country: str,
        routing_rules: dict,
        proxy_server_ips: list,
    ) -> list:
        """
        Build Xray routing rules for TUN/VPN mode.

        Bypasses proxy server IPs, SNIs, ECH Outer SNIs, and transport Host headers
        via TAG_DIRECT to prevent TUN routing loops and ECH Handshake deadlocks.
        """
        toggles = self._app_context.routing.load_toggles()
        rules: list = []

        if proxy_server_ips:
            ips = [addr for addr in proxy_server_ips if is_ip(addr)]
            domains = [addr for addr in proxy_server_ips if not is_ip(addr)]

            if ips:
                rules.append({"type": RULE_FIELD, "ip": ips, "outboundTag": TAG_DIRECT})
            if domains:
                rules.append(
                    {"type": RULE_FIELD, "domain": domains, "outboundTag": TAG_DIRECT}
                )

        # Windows NCSI probe bypass — inline domains only (no geosite dependency)
        ncsi_domains = [
            "msftconnecttest.com",
            "msftncsi.com",
            "ipv6.msftconnecttest.com",
            "www.msftconnecttest.com",
            "www.msftncsi.com",
            "dns.msftncsi.com",
            "connecttest.txt",
        ]
        rules.append(
            {"type": RULE_FIELD, "domain": ncsi_domains, "outboundTag": TAG_DIRECT}
        )

        # Direct DNS bootstrap servers to bypass TUN routing loops
        bootstrap_dns_ips = ["1.1.1.1", "8.8.8.8", "1.0.0.1", "8.8.4.4"]
        rules.append(
            {"type": RULE_FIELD, "ip": bootstrap_dns_ips, "outboundTag": TAG_DIRECT}
        )

        user_block = routing_rules.get(TAG_BLOCK, [])
        if user_block:
            rules.append(
                {"type": RULE_FIELD, "domain": user_block, "outboundTag": TAG_BLOCK}
            )

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
            rules.append(
                {"type": RULE_FIELD, "domain": user_direct, "outboundTag": TAG_DIRECT}
            )

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
            rules.append(
                {"type": RULE_FIELD, "ip": geoip_tags, "outboundTag": TAG_DIRECT}
            )
            rules.append(
                {
                    "type": RULE_FIELD,
                    "domain": [f"{GEOSITE_PREFIX}{country}"],
                    "outboundTag": TAG_DIRECT,
                }
            )

        user_proxy = routing_rules.get(TAG_PROXY, [])
        if user_proxy:
            rules.append(
                {"type": RULE_FIELD, "domain": user_proxy, "outboundTag": TAG_PROXY}
            )

        return rules
