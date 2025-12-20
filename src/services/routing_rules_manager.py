"""
Routing rules manager service.

Handles all routing-related operations:
- Adding country/user routing rules
- Managing bypass IPs
- Interface detection for direct outbound
"""

import os
import socket
from typing import Optional

from loguru import logger

from src.core.config_manager import ConfigManager
from src.core.constants import ASSETS_DIR


class RoutingRulesManager:
    """
    Manages routing rules for Xray configuration.

    Single Responsibility: Routing rules management only.
    """

    def __init__(self, config_manager: ConfigManager):
        """
        Initialize routing rules manager.

        Args:
            config_manager: Configuration manager instance
        """
        self._config_manager = config_manager
        self._primary_interface_ip: Optional[str] = None
        self._primary_interface_subnet: Optional[str] = None

    def add_routing_rules(self, config: dict):
        """
        Add routing rules for direct traffic based on selected country.

        Args:
            config: Configuration dict (modified in-place)
        """
        routing_country = self._config_manager.get_routing_country()
        if not routing_country or routing_country == "none":
            logger.info("[RoutingRulesManager] No routing country selected, skipping routing rules")
            return

        # Ensure routing section exists
        if "routing" not in config:
            config["routing"] = {"domainStrategy": "IPIfNonMatch", "rules": []}

        if "rules" not in config["routing"]:
            config["routing"]["rules"] = []

        # Map country codes to geosite/geoip tags
        country_map = {
            "ir": ("category-ir", "ir"),
            "cn": ("cn", "cn"),
            "ru": ("category-ru", "ru"),
        }

        if routing_country not in country_map:
            logger.warning(f"[RoutingRulesManager] Unknown routing country: {routing_country}")
            return

        geosite_tag, geoip_tag = country_map[routing_country]

        # Add rules at the beginning (higher priority)
        domain_rule = {
            "type": "field",
            "outboundTag": "direct",
            "domain": [f"geosite:{geosite_tag}"],
        }

        ip_rule = {
            "type": "field",
            "outboundTag": "direct",
            "ip": [f"geoip:{geoip_tag}"],
        }

        rules = [domain_rule, ip_rule]

        # Inject User Defined Rules (Highest Priority)
        user_rules = self._config_manager.load_routing_rules()

        def add_user_rule(tag, domain_list):
            if domain_list:
                ips = [d for d in domain_list if self._is_ip(d) or d.startswith("geoip:")]
                domains = [d for d in domain_list if d not in ips]

                if domains:
                    rules.insert(0, {"type": "field", "outboundTag": tag, "domain": domains})
                if ips:
                    rules.insert(0, {"type": "field", "outboundTag": tag, "ip": ips})

        add_user_rule("block", user_rules.get("block", []))
        add_user_rule("proxy", user_rules.get("proxy", []))
        add_user_rule("direct", user_rules.get("direct", []))

        # Assign back
        config["routing"]["rules"] = rules + config["routing"]["rules"]

        direct_rules = len(user_rules.get("direct", []))
        proxy_rules = len(user_rules.get("proxy", []))
        block_rules = len(user_rules.get("block", []))
        total_rules = direct_rules + proxy_rules + block_rules
        logger.info(f"[RoutingRulesManager] Added routing rules. Country: {routing_country}, User Rules: {total_rules}")

    def get_bypass_ips(self, config: dict) -> list:
        """
        Extract IPs to bypass for TUN mode.

        Args:
            config: Configuration dict

        Returns:
            List of IPs to bypass
        """
        bypass_list = []

        # 1. Bypass main proxy server IP
        for outbound in config.get("outbounds", []):
            protocol = outbound.get("protocol")
            if protocol in ["vless", "vmess", "trojan", "shadowsocks"]:
                settings = outbound.get("settings", {})
                server_obj = None
                if "vnext" in settings and settings["vnext"]:
                    server_obj = settings["vnext"][0]
                elif "servers" in settings and settings["servers"]:
                    server_obj = settings["servers"][0]

                if server_obj and "address" in server_obj:
                    bypass_list.append(server_obj["address"])
                    break

        # 2. Bypass primary interface IP/subnet
        if self._primary_interface_ip:
            bypass_list.append(self._primary_interface_ip)
        if self._primary_interface_subnet:
            bypass_list.append(self._primary_interface_subnet)

        # 3. Add custom DNS servers
        dns_servers = self._config_manager.get_custom_dns().split(",")
        for dns in dns_servers:
            dns = dns.strip()
            if dns:
                bypass_list.append(dns)

        # 4. Optional: country-specific bypass ranges
        routing_country = self._config_manager.get_routing_country()
        if routing_country and routing_country != "none":
            bypass_file = os.path.join(ASSETS_DIR, f"{routing_country}_bypass.txt")
            if os.path.exists(bypass_file):
                try:
                    with open(bypass_file, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                bypass_list.append(line)
                except Exception as e:
                    logger.error(f"[RoutingRulesManager] Failed to load bypass file: {e}")

        return bypass_list

    def bind_direct_outbound(self, config: dict):
        """
        Detect primary interface for TUN bypass purposes.

        Args:
            config: Configuration dict
        """
        try:
            from src.utils.network_interface import NetworkInterfaceDetector

            # Detect primary network interface
            interface_name, interface_ip, subnet, _ = NetworkInterfaceDetector.get_primary_interface()

            if not interface_ip:
                logger.warning("[RoutingRulesManager] Could not detect primary interface for TUN bypass.")
                return

            logger.info(
                f"[RoutingRulesManager] Detected primary interface: {interface_name} ({interface_ip}, {subnet})"
            )

            # Store for TUN bypass
            self._primary_interface_ip = interface_ip
            self._primary_interface_subnet = subnet

        except Exception as e:
            logger.error(f"[RoutingRulesManager] Failed to detect interface: {e}")

    def _is_ip(self, val: str) -> bool:
        """Check if string is IP or standard Xray IP format."""
        if val.startswith("geoip:") or "/" in val:  # CIDR
            return True
        try:
            socket.inet_aton(val)
            return True
        except Exception:
            return False
