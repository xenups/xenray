"""
Xray configuration processor service.

Handles all Xray-specific configuration processing:
- DNS resolution and SNI patching
- Stream settings configuration
- SOCKS port extraction
- DNS configuration
- Server IP extraction
"""

import json
import os
import socket
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
        new_config = json.loads(json.dumps(config))

        # Ensure log settings
        new_config["log"] = {"loglevel": "info", "access": "", "error": ""}

        # Ensure asset location
        os.environ["XRAY_LOCATION_ASSET"] = XRAY_LOCATION_ASSET

        # Force IP Strategy: Resolve domain and patch config
        self._resolve_and_patch_config(new_config)

        # Configure DNS (User Settings)
        self.configure_dns(new_config)

        return new_config

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

        config["dns"]["servers"] = servers

        # Ensure query strategy
        if "queryStrategy" not in config["dns"]:
            config["dns"]["queryStrategy"] = "UseIP"

        logger.info(f"[XrayConfigProcessor] Configured DNS with {len(servers)} servers")

    def _resolve_and_patch_config(self, config: dict):
        """
        Resolve domains to IPs and patch SNI/Host settings.

        Args:
            config: Configuration dict (modified in-place)
        """
        for outbound in config.get("outbounds", []):
            protocol = outbound.get("protocol")
            if protocol not in self.SUPPORTED_PROTOCOLS:
                continue

            settings = outbound.get("settings", {})
            server_obj = self._get_server_object(settings)

            if not server_obj or "address" not in server_obj:
                continue

            domain = server_obj["address"]

            # Attempt to resolve domain to IP
            ip = self._resolve_domain_to_ip(domain, timeout=self.DNS_TIMEOUT)

            if ip:
                # SUCCESS: Replace address with IP
                server_obj["address"] = ip
                logger.info(f"[XrayConfigProcessor] Replaced address {domain} with resolved IP {ip}")
            else:
                # FALLBACK: Keep domain
                logger.warning(
                    f"[XrayConfigProcessor] DNS resolution failed for {domain}. "
                    "Keeping domain address and relying on Xray internal DNS/routing."
                )
                server_obj["address"] = domain

            # Patch stream settings with original domain
            try:
                self._patch_stream_settings(outbound, domain)
            except Exception as e:
                logger.error(f"[XrayConfigProcessor] Failed to patch stream settings for {domain}: {e}")

    def _resolve_domain_to_ip(self, domain: str, timeout: float = 5.0) -> Optional[str]:
        """
        Resolve domain to IP address with timeout.

        Args:
            domain: Domain name
            timeout: Resolution timeout

        Returns:
            IP address or None
        """
        # Check if it's already an IP
        try:
            socket.inet_aton(domain)
            return domain  # Already an IP
        except (socket.error, OSError):
            pass  # It's a domain, need to resolve

        try:
            # Set socket timeout
            socket.setdefaulttimeout(timeout)
            ip = socket.gethostbyname(domain)
            logger.info(f"[XrayConfigProcessor] Resolved {domain} to {ip}")
            return ip
        except (socket.gaierror, socket.timeout, OSError) as e:
            logger.error(f"[XrayConfigProcessor] Failed to resolve {domain}: {e}")
            return None
        finally:
            # Reset timeout
            socket.setdefaulttimeout(None)

    def _get_server_object(self, settings: dict) -> Optional[dict]:
        """Extract server object from settings based on protocol."""
        if "vnext" in settings and settings["vnext"]:
            return settings["vnext"][0]
        elif "servers" in settings and settings["servers"]:
            return settings["servers"][0]
        return None

    def _patch_stream_settings(self, outbound: dict, domain: str):
        """Patch stream settings (TLS, Reality, WS, HTTPUpgrade) with domain."""
        stream_settings = outbound.setdefault("streamSettings", {})
        security = stream_settings.get("security", "none")
        network = stream_settings.get("network", "")

        # Patch security settings
        if security == "tls":
            self._patch_tls_settings(stream_settings, domain)
        elif security == "reality":
            self._patch_reality_settings(stream_settings, domain)

        # Sanitize network
        if network == "udp":
            logger.warning("[XrayConfigProcessor] Removed invalid 'udp' network from streamSettings")
            stream_settings.pop("network", None)
            network = ""

        # Patch network settings
        if network == "ws":
            self._patch_ws_settings(stream_settings, domain)
        elif network == "httpupgrade":
            self._patch_httpupgrade_settings(stream_settings, domain)

    def _patch_tls_settings(self, stream_settings: dict, domain: str):
        """Patch TLS settings with SNI."""
        tls_settings = stream_settings.setdefault("tlsSettings", {})
        if not tls_settings.get("serverName"):
            tls_settings["serverName"] = domain
            logger.info(f"[XrayConfigProcessor] Set TLS SNI to {domain}")

    def _patch_reality_settings(self, stream_settings: dict, domain: str):
        """Patch Reality settings with SNI."""
        reality_settings = stream_settings.setdefault("realitySettings", {})
        if not reality_settings.get("serverName"):
            reality_settings["serverName"] = domain
            logger.info(f"[XrayConfigProcessor] Set Reality SNI to {domain}")

    def _patch_ws_settings(self, stream_settings: dict, domain: str):
        """Patch WebSocket settings with Host header."""
        ws_settings = stream_settings.setdefault("wsSettings", {})
        headers = ws_settings.setdefault("headers", {})
        if not headers.get("Host"):
            headers["Host"] = domain
            logger.info(f"[XrayConfigProcessor] Set WS Host to {domain}")

    def _patch_httpupgrade_settings(self, stream_settings: dict, domain: str):
        """Patch HTTPUpgrade settings with host."""
        httpupgrade_settings = stream_settings.setdefault("httpupgradeSettings", {})
        if not httpupgrade_settings.get("host"):
            httpupgrade_settings["host"] = domain
            logger.info(f"[XrayConfigProcessor] Set HTTPUpgrade Host to {domain}")
