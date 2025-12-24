"""
Xray configuration processor service.

Handles all Xray-specific configuration processing:
- DNS resolution and SNI patching
- Stream settings configuration
- SOCKS port extraction
- DNS configuration
- Server IP extraction
"""

import copy
import os
from typing import Optional

from loguru import logger

from src.core.config_manager import ConfigManager
from src.core.constants import XRAY_LOCATION_ASSET


class XrayConfigProcessor:
    """
    Processes Xray configurations.

    Single Responsibility: Xray configuration processing only.
    """

    SUPPORTED_PROTOCOLS = ["vless", "vmess", "trojan", "shadowsocks", "hysteria2"]
    DNS_TIMEOUT = 5.0  # seconds

    def __init__(self, config_manager: ConfigManager):
        """
        Initialize Xray config processor.

        Args:
            config_manager: Configuration manager instance
        """
        self._config_manager = config_manager

    def process_config(self, config: dict) -> dict:
        """
        Process config for Xray usage.

        Args:
            config: Raw configuration

        Returns:
            Processed configuration
        """
        # Deep copy to avoid modifying original
        new_config = copy.deepcopy(config)

        # Ensure log settings
        new_config["log"] = {"loglevel": "info", "access": "", "error": ""}

        # Ensure asset location
        os.environ["XRAY_LOCATION_ASSET"] = XRAY_LOCATION_ASSET

        # Add inbounds with user's port settings (if not already present)
        self._ensure_inbounds(new_config)

        # Configure DNS (User Settings)
        self.configure_dns(new_config)

        # CRITICAL: Resolve outbound server addresses to IPs
        # This allows ALL DNS queries to go through the tunnel after connection
        # No bootstrap DNS needed - we resolve once before Xray starts
        self._resolve_outbound_addresses(new_config)

        # Safe Fallbacks (Non-destructive)
        self._safe_patch_config(new_config)

        return new_config

    def _ensure_inbounds(self, config: dict):
        """
        Ensure inbounds exist with user's configured ports.

        Args:
            config: Configuration dict (modified in-place)
        """
        # Get user configured port
        user_port = self._config_manager.get_proxy_port()

        # Check if inbounds already exist
        if not config.get("inbounds"):
            config["inbounds"] = []

        # Add SOCKS inbound if not present
        socks_exists = any(ib.get("protocol") == "socks" for ib in config["inbounds"])
        if not socks_exists:
            config["inbounds"].append(
                {
                    "tag": "socks",
                    "port": user_port,
                    "listen": "127.0.0.1",
                    "protocol": "socks",
                    "settings": {"udp": True},
                    "sniffing": {
                        "enabled": True,
                        "destOverride": ["http", "tls", "quic"],
                        "metadataOnly": False,
                    },
                }
            )
            logger.info(f"[XrayConfigProcessor] Added SOCKS inbound on port {user_port}")
        else:
            # Update existing SOCKS port and add sniffing
            for inbound in config["inbounds"]:
                if inbound.get("protocol") == "socks":
                    inbound["port"] = user_port
                    inbound["sniffing"] = {
                        "enabled": True,
                        "destOverride": ["http", "tls", "quic"],
                        "metadataOnly": False,
                    }
        # Add HTTP inbound if not present
        http_exists = any(ib.get("protocol") == "http" for ib in config["inbounds"])
        if not http_exists:
            config["inbounds"].append(
                {
                    "tag": "http",
                    "port": user_port + 4,  # Default: 10809 if SOCKS is 10805
                    "listen": "127.0.0.1",
                    "protocol": "http",
                }
            )
            logger.info(f"[XrayConfigProcessor] Added HTTP inbound on port {user_port + 4}")

    def _resolve_outbound_addresses(self, config: dict):
        """
        Resolve outbound server domain names to IPs before Xray starts.
        This eliminates the bootstrap DNS problem - all DNS can go through tunnel.

        Args:
            config: Configuration dict (modified in-place)
        """
        import socket

        for outbound in config.get("outbounds", []):
            protocol = outbound.get("protocol")
            if protocol not in self.SUPPORTED_PROTOCOLS:
                continue

            settings = outbound.get("settings", {})
            server_obj = self._get_server_object(settings)

            if not server_obj or "address" not in server_obj:
                continue

            address = server_obj["address"]
            # Skip if already an IP
            if self._is_ip(address):
                logger.debug(f"[XrayConfigProcessor] Address {address} is already an IP, skipping resolution")
                continue

            # Resolve domain to IP using system DNS (bootstrap)
            try:
                socket.setdefaulttimeout(5.0)
                resolved_ip = socket.gethostbyname(address)
                server_obj["address"] = resolved_ip
                logger.info(f"Bootstrap: Resolved {address} → {resolved_ip}")
                logger.info("All DNS queries will now go through tunnel")
            except (socket.gaierror, socket.timeout, OSError) as e:
                logger.error(f"Failed to resolve {address}: {e}")
                logger.warning("Keeping domain address - may cause DNS issues")
            finally:
                socket.setdefaulttimeout(None)

    def validate_config(self, config: dict) -> tuple[bool, str]:
        """
        Validate Xray configuration structure and values.

        Args:
            config: Configuration dict to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not config or not isinstance(config, dict):
            return False, "Config must be a non-empty dictionary"

        # Check for required outbounds
        if "outbounds" not in config or not isinstance(config["outbounds"], list):
            return False, "Config must have 'outbounds' list"

        if len(config["outbounds"]) == 0:
            return False, "At least one outbound is required"

        # Validate outbounds
        for idx, outbound in enumerate(config["outbounds"]):
            if not isinstance(outbound, dict):
                return False, f"Outbound {idx} must be a dictionary"

            protocol = outbound.get("protocol")
            if not protocol:
                return False, f"Outbound {idx} missing 'protocol'"

            if protocol in self.SUPPORTED_PROTOCOLS:
                settings = outbound.get("settings", {})
                server_obj = self._get_server_object(settings)
                if server_obj:
                    # Validate port
                    port = server_obj.get("port")
                    if port and not (1 <= port <= 65535):
                        return False, f"Outbound {idx} has invalid port: {port}"

        # Validate inbounds if present
        if "inbounds" in config:
            for idx, inbound in enumerate(config["inbounds"]):
                port = inbound.get("port")
                if port and not (1 <= port <= 65535):
                    return False, f"Inbound {idx} has invalid port: {port}"

        return True, ""

    def get_socks_port(self, config: dict) -> int:
        """
        Extract SOCKS port from config and inject sniffing settings.

        Args:
            config: Configuration dict

        Returns:
            SOCKS port number
        """
        # Get user configured port
        user_port = self._config_manager.get_proxy_port()

        # Update the config to listen on this port and inject Sniffing
        for inbound in config.get("inbounds", []):
            if inbound.get("protocol") == "socks":
                inbound["port"] = user_port

                # CRITICAL FIX: Inject Sniffing to capture the domain name
                inbound["sniffing"] = {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                    "metadataOnly": False,
                }
                logger.debug("[XrayConfigProcessor] Injected Sniffing settings into Xray SOCKS inbound.")

        return user_port

    def get_proxy_server_ip(self, config: dict) -> list[str]:
        """
        Extract proxy server IPs/domains from config.

        Args:
            config: Configuration dict

        Returns:
            List of server addresses
        """
        addresses = []
        for outbound in config.get("outbounds", []):
            if outbound.get("protocol") in ["vless", "vmess", "trojan", "shadowsocks"]:
                settings = outbound.get("settings", {})
                if "vnext" in settings:  # VLESS/VMess
                    for server in settings["vnext"]:
                        addr = server.get("address", "")
                        if addr:
                            addresses.append(addr)
                elif "servers" in settings:  # Trojan/Shadowsocks
                    for server in settings["servers"]:
                        addr = server.get("address", "")
                        if addr:
                            addresses.append(addr)
        return list(set(addresses))  # Unique addresses

    def is_quic_transport(self, config: dict) -> bool:
        """
        Detect if QUIC/HTTP3 transport is used.

        Args:
            config: Configuration dict

        Returns:
            True if QUIC is detected
        """
        for outbound in config.get("outbounds", []):
            stream_settings = outbound.get("streamSettings", {})
            network = stream_settings.get("network", "")
            if network in ["quic", "http3"]:
                return True
        return False

    def configure_dns(self, config: dict):
        """
        Configure DNS based on user settings.

        Args:
            config: Configuration dict (modified in-place)
        """
        dns_config = self._config_manager.load_dns_config()

        servers = []
        for item in dns_config:
            addr = item.get("address", "")
            if not addr:
                continue

            proto = item.get("protocol", "udp")

            # Construct server entry string
            if proto == "doh":
                if not addr.startswith("https://"):
                    addr = f"https://{addr}/dns-query"
            elif proto == "dot":
                if not addr.startswith("tls://"):
                    addr = f"tls://{addr}"
            elif proto == "doq":
                if not addr.startswith("quic://"):
                    addr = f"quic://{addr}"

            # Create full object if domains specified
            domains = item.get("domains", [])
            if domains:
                entry = {"address": addr, "domains": domains}
            else:
                entry = addr

            servers.append(entry)

        # Inject into config
        if "dns" not in config:
            config["dns"] = {}

        config["dns"]["servers"] = servers if servers else ["1.1.1.1", "8.8.8.8"]

        # All DNS queries will go through tunnel (outbound uses IP)
        if "queryStrategy" not in config["dns"]:
            config["dns"]["queryStrategy"] = "UseIP"

        logger.info(
            f"[XrayConfigProcessor] Configured {len(config['dns']['servers'])} DNS server(s) - all queries via tunnel"
        )

    def _safe_patch_config(self, config: dict):
        """
        Apply context-aware fallbacks only if fields are missing.
        Strictly follows the "no-override" and "parser-intent" rules.
        """
        fallback_count = 0
        for outbound in config.get("outbounds", []):
            protocol = outbound.get("protocol")
            if protocol not in self.SUPPORTED_PROTOCOLS:
                continue

            settings = outbound.get("settings", {})
            server_obj = self._get_server_object(settings)
            if not server_obj or "address" not in server_obj:
                continue

            domain = server_obj["address"]

            # Apply fallbacks only if missing
            applied = self._apply_safe_stream_fallbacks(outbound, domain)
            if applied:
                fallback_count += 1
        if fallback_count > 0:
            logger.info(f"[XrayConfigProcessor] Applied safe fallbacks to {fallback_count} outbound(s)")

    def _apply_safe_stream_fallbacks(self, outbound: dict, domain: str) -> bool:
        """
        Safe fallbacks for stream settings (SNI/Host) if missing.

        Returns:
            True if any fallback was applied
        """
        applied = False
        stream_settings = outbound.setdefault("streamSettings", {})
        security = stream_settings.get("security", "none")
        network = stream_settings.get("network", "")

        # 1. SNI Fallback (tls/reality)
        if security in ("tls", "reality") and security != "none":
            field = "tlsSettings" if security == "tls" else "realitySettings"
            sec_settings = stream_settings.setdefault(field, {})
            if not sec_settings.get("serverName"):
                # Missing SNI - use address as fallback (standard Xray behavior)
                # But only if domain is NOT an IP (safe optimization)
                if not self._is_ip(domain):
                    sec_settings["serverName"] = domain
                    logger.info(f"[XrayConfigProcessor] Fallback: Set {field}.serverName = {domain}")
                    applied = True

        # 2. Host Fallback (ws/httpupgrade/xhttp)
        if network == "ws":
            ws_settings = stream_settings.setdefault("wsSettings", {})
            headers = ws_settings.setdefault("headers", {})
            if not headers.get("Host") and not self._is_ip(domain):
                headers["Host"] = domain
                logger.info(f"[XrayConfigProcessor] Fallback: Set wsSettings.headers.Host = {domain}")
                applied = True
        elif network == "httpupgrade":
            hu_settings = stream_settings.setdefault("httpupgradeSettings", {})
            if not hu_settings.get("host") and not self._is_ip(domain):
                hu_settings["host"] = domain
                logger.info(f"[XrayConfigProcessor] Fallback: Set httpupgradeSettings.host = {domain}")
                applied = True
        elif network == "xhttp":
            xhttp_settings = stream_settings.setdefault("xhttpSettings", {})
            if not xhttp_settings.get("host") and not self._is_ip(domain):
                xhttp_settings["host"] = domain
                logger.info(f"[XrayConfigProcessor] Fallback: Set xhttpSettings.host = {domain}")
                applied = True

            # XHTTP Stability: Set mode to packet-up for best CDN compatibility if not specified
            # packet-up = "packetized uplink, streaming downlink" - most reliable for CDNs
            if not xhttp_settings.get("mode"):
                xhttp_settings["mode"] = "packet-up"
                logger.info("[XrayConfigProcessor] Set xhttpSettings.mode = packet-up for stability")
                applied = True

            # XMUX: Add connection cycling to prevent stalls (if not configured)
            # These defaults prevent connection timeouts and Nginx request limits
            if "xmux" not in xhttp_settings:
                xhttp_settings["xmux"] = {
                    "maxConcurrency": "16-32",  # Default from Xray docs - random range
                    "hMaxReusableSecs": "1800-3000",  # Cycle connections every 30-50 min
                    "hMaxRequestTimes": "600-900",  # Stay under Nginx's 1000 limit
                }
                logger.info("[XrayConfigProcessor] Added XMUX settings for connection stability")
                applied = True

        return applied

    def _get_server_object(self, settings: dict) -> Optional[dict]:
        """Extract server object from settings."""
        if "vnext" in settings and settings["vnext"]:
            return settings["vnext"][0]
        elif "servers" in settings and settings["servers"]:
            return settings["servers"][0]
        return None

    def _is_ip(self, address: str) -> bool:
        """Check if address is an IP (IPv4 or IPv6)."""
        import ipaddress

        try:
            ipaddress.ip_address(address)
            return True
        except ValueError:
            return False
