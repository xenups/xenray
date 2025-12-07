"""Connection Manager."""

import json
import os
import subprocess
from typing import Optional

from loguru import logger

from src.core.config_manager import ConfigManager
from src.core.constants import OUTPUT_CONFIG_PATH, XRAY_LOCATION_ASSET, ASSETS_DIR
from src.services.singbox_service import SingboxService
from src.services.xray_service import XrayService


class ConnectionManager:
    """Manages VPN/Proxy connections."""

    def __init__(self, config_manager: ConfigManager):
        self._config_manager = config_manager
        self._xray_service = XrayService()
        self._singbox_service = SingboxService()
        self._current_connection = None

    def connect(self, file_path: str, mode: str, step_callback=None) -> bool:
        """
        Establish connection.
        mode: 'proxy' or 'vpn'
        step_callback: Optional callback for reporting connection steps
        """
        def report_step(msg):
            if step_callback:
                step_callback(msg)
        
        # Load config
        report_step("Loading configuration...")
        logger.debug(f"Loading config from {file_path}")
        config, _ = self._config_manager.load_config(file_path)
        if not config:
            logger.error("Failed to load config")
            return False

        # Stop existing processes if any (don't call full disconnect to avoid race)
        if self._current_connection:
            report_step("Stopping existing connection...")
            logger.debug("Stopping existing connection")
            if self._current_connection.get("xray_pid"):
                self._xray_service.stop()
            if self._current_connection.get("singbox_pid"):
                self._singbox_service.stop()

        # Process config for Xray
        report_step("Processing configuration...")
        logger.debug("Processing configuration")
        processed_config = self._process_config(config)

        # Save processed config
        logger.debug(f"Saving processed config to {OUTPUT_CONFIG_PATH}")
        with open(OUTPUT_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(processed_config, f, indent=2)
        logger.debug("Config saved successfully")

        # Start Xray
        report_step("Starting Xray...")
        logger.debug("Starting Xray service")
        xray_pid = self._xray_service.start(OUTPUT_CONFIG_PATH)
        if not xray_pid:
            logger.error("Failed to start Xray")
            return False
        logger.debug(f"Xray started with PID {xray_pid}")

        # Start Sing-box if VPN mode
        singbox_pid = None

        if mode == "vpn":
            report_step("Initializing VPN tunnel...")
            socks_port = self._get_socks_port(processed_config)
            routing_country = self._config_manager.get_routing_country()
            proxy_server_ip = self._get_proxy_server_ip(processed_config)
            gateway_ip = self._get_default_gateway()

            # singbox_pid = self._singbox_service.start(socks_port, routing_country, proxy_server_ip, gateway_ip)
            singbox_pid = self._singbox_service.start(
                socks_port,
                proxy_server_ip,
                gateway_ip,
                routing_country,
            )
            if not singbox_pid:
                self._xray_service.stop()
                return False

        report_step("Finalizing connection...")
        self._current_connection = {
            "mode": mode,
            "xray_pid": xray_pid,
            "singbox_pid": singbox_pid,
            "file": file_path,
        }
        return True

    def disconnect(self) -> bool:
        """Disconnect current connection."""
        if not self._current_connection:
            return True

        # Stop Sing-box first
        if self._current_connection.get("singbox_pid"):
            self._singbox_service.stop()

        # Stop Xray
        if self._current_connection["xray_pid"]:
            self._xray_service.stop()

        self._current_connection = None
        return True

    def _process_config(self, config: dict) -> dict:
        """
        Process config for Xray usage.
        Note: Routing is now handled by Sing-box, so we only do basic processing.
        """
        # Deep copy to avoid modifying original
        new_config = json.loads(json.dumps(config))

        # Ensure log settings
        new_config["log"] = {"loglevel": "info", "access": "", "error": ""}

        # Ensure asset location
        os.environ["XRAY_LOCATION_ASSET"] = XRAY_LOCATION_ASSET

        # Force IP Strategy: Resolve domain and patch config
        self._resolve_and_patch_config(new_config)

        return new_config

    def _resolve_domain_to_ip(self, domain: str, timeout: float = 5.0) -> Optional[str]:
        """
        Resolve domain to IP address with timeout.
        
        Args:
            domain: Domain name to resolve
            timeout: Timeout in seconds (default: 5.0)
            
        Returns:
            IP address as string, or None if resolution fails
        """
        import socket
        
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
            logger.info(f"[ConnectionManager] Resolved {domain} to {ip}")
            return ip
        except (socket.gaierror, socket.timeout, OSError) as e:
            logger.error(f"[ConnectionManager] Failed to resolve {domain}: {e}")
            return None
        finally:
            # Reset timeout
            socket.setdefaulttimeout(None)
    
    def _patch_tls_settings(self, stream_settings: dict, domain: str):
        """Patch TLS settings with SNI."""
        tls_settings = stream_settings.setdefault("tlsSettings", {})
        if not tls_settings.get("serverName"):
            tls_settings["serverName"] = domain
            logger.info(f"[ConnectionManager] Set TLS SNI to {domain}")
    
    def _patch_reality_settings(self, stream_settings: dict, domain: str):
        """Patch Reality settings with SNI."""
        reality_settings = stream_settings.setdefault("realitySettings", {})
        if not reality_settings.get("serverName"):
            reality_settings["serverName"] = domain
            logger.info(f"[ConnectionManager] Set Reality SNI to {domain}")
    
    def _patch_ws_settings(self, stream_settings: dict, domain: str):
        """Patch WebSocket settings with Host header."""
        ws_settings = stream_settings.setdefault("wsSettings", {})
        headers = ws_settings.setdefault("headers", {})
        if not headers.get("Host"):
            headers["Host"] = domain
            logger.info(f"[ConnectionManager] Set WS Host to {domain}")
    
    def _patch_httpupgrade_settings(self, stream_settings: dict, domain: str):
        """Patch HTTPUpgrade settings with host."""
        httpupgrade_settings = stream_settings.setdefault("httpupgradeSettings", {})
        if not httpupgrade_settings.get("host"):
            httpupgrade_settings["host"] = domain
            logger.info(f"[ConnectionManager] Set HTTPUpgrade Host to {domain}")
    
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
        
        # Patch network settings
        if network == "ws":
            self._patch_ws_settings(stream_settings, domain)
        elif network == "httpupgrade":
            self._patch_httpupgrade_settings(stream_settings, domain)
    
    def _get_server_object(self, settings: dict) -> Optional[dict]:
        """Extract server object from settings based on protocol."""
        if "vnext" in settings and settings["vnext"]:
            return settings["vnext"][0]
        elif "servers" in settings and settings["servers"]:
            return settings["servers"][0]
        return None
    
    def _resolve_and_patch_config(self, config: dict):
        """
        Finds the proxy server address, resolves it to an IP,
        replaces the address with the IP, and sets SNI/Host to the original domain.
        
        This method processes all outbounds and patches their configurations.
        """
        SUPPORTED_PROTOCOLS = ["vless", "vmess", "trojan", "shadowsocks"]
        DNS_TIMEOUT = 5.0  # seconds

        for outbound in config.get("outbounds", []):
            protocol = outbound.get("protocol")
            if protocol not in SUPPORTED_PROTOCOLS:
                continue
                
            settings = outbound.get("settings", {})
            server_obj = self._get_server_object(settings)
            
            if not server_obj or "address" not in server_obj:
                continue
            
            domain = server_obj["address"]
            
            # Resolve domain to IP
            ip = self._resolve_domain_to_ip(domain, timeout=DNS_TIMEOUT)
            if not ip:
                continue  # Skip if resolution failed
            
            # Replace address with IP
            server_obj["address"] = ip
            
            # Patch stream settings with original domain
            try:
                self._patch_stream_settings(outbound, domain)
            except Exception as e:
                logger.error(f"[ConnectionManager] Failed to patch stream settings for {domain}: {e}")

    def _get_socks_port(self, config: dict) -> int:
        """Extract SOCKS port from config, overriding with user preference."""
        # Get user configured port
        user_port = self._config_manager.get_proxy_port()

        # We also need to update the config to listen on this port
        # This is a bit tricky because we need to find the inbound and update it
        for inbound in config.get("inbounds", []):
            if inbound.get("protocol") == "socks":
                inbound["port"] = user_port
            elif inbound.get("protocol") == "http":
                # Usually we want http port to be different, or maybe same if sniffing?
                # For now let's just update socks port as that's what tun2proxy uses
                pass

        return user_port

    def _get_proxy_server_ip(self, config: dict) -> list[str]:
        """
        Extract proxy server IPs/domains from config.
        Returns a list of all server addresses found.
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

    def _get_default_gateway(self) -> str:
        """
        Get the default gateway IP address.
        """
        try:
            # Use PowerShell to get default gateway
            cmd = 'Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Select-Object -ExpandProperty NextHop'
            result = subprocess.check_output(["powershell", "-Command", cmd], text=True).strip()
            # Handle multiple gateways if present (take the first one)
            if '\n' in result:
                result = result.split('\n')[0].strip()
            return result
        except Exception as e:
            logger.error(f"[ConnectionManager] Failed to get default gateway: {e}")
            return ""

    def _get_bypass_ips(self, config: dict) -> list:
        """
        Extract IPs to bypass for TUN mode.
        Ensures:
        1. Proxy server IP is bypassed.
        2. Primary interface IP/subnet is bypassed.
        3. Custom DNS servers are bypassed.
        4. Country-specific ranges can be bypassed if enabled.
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
                    break  # Only the first/main proxy

        # 2. Bypass primary interface IP/subnet (for local network)
        if hasattr(self, "_primary_interface_ip") and self._primary_interface_ip:
            bypass_list.append(self._primary_interface_ip)
        if hasattr(self, "_primary_interface_subnet") and self._primary_interface_subnet:
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
                    logger.error(f"[ConnectionManager] Failed to load bypass file: {e}")

        return bypass_list


    def _bind_direct_outbound(self, config: dict):
        """
        Detect primary interface for TUN bypass purposes.
        Ensures DNS and local traffic is reachable without enabling direct routing.
        """
        try:
            from src.utils.network_interface import NetworkInterfaceDetector

            # Detect primary network interface
            interface_name, interface_ip, subnet = NetworkInterfaceDetector.get_primary_interface()

            if not interface_ip:
                logger.warning("[ConnectionManager] Could not detect primary interface for TUN bypass.")
                return

            logger.info(f"[ConnectionManager] Detected primary interface: {interface_name} ({interface_ip}, {subnet})")

            # Store for TUN bypass
            self._primary_interface_ip = interface_ip
            self._primary_interface_subnet = subnet

        except Exception as e:
            logger.error(f"[ConnectionManager] Failed to detect interface: {e}")

    def _add_routing_rules(self, config: dict):
        """
        Add routing rules for direct traffic based on selected country.
        Injects rules to route country-specific traffic to 'direct' outbound.
        """
        routing_country = self._config_manager.get_routing_country()
        if not routing_country or routing_country == "none":
            logger.info(
                "[ConnectionManager] No routing country selected, skipping routing rules"
            )
            return

        # Ensure routing section exists
        if "routing" not in config:
            config["routing"] = {"domainStrategy": "IPIfNonMatch", "rules": []}

        if "rules" not in config["routing"]:
            config["routing"]["rules"] = []

        # Map country codes to geosite/geoip tags
        country_map = {
            "ir": ("category-ir", "ir"),  # (geosite tag, geoip tag)
            "cn": ("cn", "cn"),
            "ru": ("category-ru", "ru"),
        }

        if routing_country not in country_map:
            logger.warning(
                f"[ConnectionManager] Unknown routing country: {routing_country}"
            )
            return

        geosite_tag, geoip_tag = country_map[routing_country]

        # Add rules at the beginning (higher priority)
        # Rule 1: Route country domains to direct
        domain_rule = {
            "type": "field",
            "outboundTag": "direct",
            "domain": [f"geosite:{geosite_tag}"],
        }

        # Rule 2: Route country IPs to direct
        ip_rule = {
            "type": "field",
            "outboundTag": "direct",
            "ip": [f"geoip:{geoip_tag}"],
        }

        # Insert at beginning for higher priority
        config["routing"]["rules"].insert(0, ip_rule)
        config["routing"]["rules"].insert(0, domain_rule)

        logger.info(
            f"[ConnectionManager] Added routing rules for {routing_country}: geosite:{geosite_tag}, geoip:{geoip_tag}"
        )
