"""Connection Manager."""

import json
import os
import socket
import subprocess
from typing import Optional

from loguru import logger

from src.core.config_manager import ConfigManager
from src.core.constants import ASSETS_DIR, OUTPUT_CONFIG_PATH, XRAY_LOCATION_ASSET
from src.core.i18n import t
from src.services.singbox_service import SingboxService
from src.services.xray_service import XrayService


class ConnectionManager:
    """Manages VPN/Proxy connections."""

    def __init__(self, config_manager: ConfigManager):
        self._config_manager = config_manager
        self._xray_service = XrayService()
        self._singbox_service = SingboxService()
        self._current_connection = None
        self._primary_interface_ip: Optional[str] = None
        self._primary_interface_subnet: Optional[str] = None

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
        report_step(t("connection.loading_config"))
        logger.debug(f"Loading config from {file_path}")
        config, _ = self._config_manager.load_config(file_path)
        if not config:
            logger.error("Failed to load config")
            return False

        # Check Internet Connectivity
        report_step(t("connection.checking_network"))
        if not self._check_internet_connection():
            logger.error("No internet connection detected")
            report_step(t("connection.no_internet"))
            return False

        # Stop existing processes if any (don't call full disconnect to avoid race)
        if self._current_connection:
            report_step(t("connection.stopping_existing"))
            logger.debug("Stopping existing connection")
            if self._current_connection.get("xray_pid"):
                self._xray_service.stop()
            if self._current_connection.get("singbox_pid"):
                self._singbox_service.stop()

        # Process config for Xray (Resolve to IP, Patch SNI, Ensure Sniffing)
        report_step(t("connection.processing_config"))
        logger.debug("Processing configuration")
        # 1. Resolve Outbound and Patch SNI
        processed_config = self._process_config(config)

        # 2. Inject Sniffing and Port for Xray Inbound (CRITICAL FIX)
        socks_port = self._get_socks_port(processed_config)

        # Save processed config
        logger.debug(f"Saving processed config to {OUTPUT_CONFIG_PATH}")
        try:
            with open(OUTPUT_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(processed_config, f, indent=2)
            logger.debug("Config saved successfully")
        except Exception as e:
            logger.error(f"Failed to save Xray config: {e}")
            return False

        # Start Xray
        report_step(t("connection.starting_xray"))
        logger.debug("Starting Xray service")
        xray_pid = self._xray_service.start(OUTPUT_CONFIG_PATH)
        if not xray_pid:
            logger.error("Failed to start Xray")
            return False
        logger.debug(f"Xray started with PID {xray_pid}")

        # Start Sing-box if VPN mode
        singbox_pid = None

        if mode == "vpn":
            report_step(t("connection.initializing_vpn"))

            # Since _get_socks_port updated the config, socks_port is valid
            routing_country = self._config_manager.get_routing_country()
            proxy_server_ip = self._get_proxy_server_ip(processed_config)
            gateway_ip = self._get_default_gateway()

            # Pass required parameters to Sing-box service
            # Load routing rules for Sing-box injection (Consistent Routing)
            routing_rules = self._config_manager.load_routing_rules()

            singbox_pid = self._singbox_service.start(
                xray_socks_port=socks_port,
                proxy_server_ip=proxy_server_ip,
                gateway_ip=gateway_ip,
                routing_country=routing_country,
                routing_rules=routing_rules,
            )
            if not singbox_pid:
                logger.error("Failed to start Sing-box. Stopping Xray.")
                self._xray_service.stop()
                return False

        report_step(t("connection.finalizing"))
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

    def _check_internet_connection(self) -> bool:
        """
        Check if there is an active internet connection.
        """
        # 1. Check if we have a default gateway (basic network config check)
        gateway = self._get_default_gateway()
        if not gateway:
            logger.warning("[ConnectionManager] No default gateway found.")
            # We fail here because if there's no gateway, we can't route anywhere.
            # Exception: User might be on a weird specialized network, but for general VPN use, this is a blocker.
            return False

        # 2. Check actual connectivity to a high-availability host
        # We use standard DNS ports (53) which are rarely blocked, unlike ICMP
        test_hosts = [
            ("8.8.8.8", 53),  # Google DNS
            ("1.1.1.1", 53),  # Cloudflare DNS
            ("208.67.222.222", 53),  # OpenDNS
        ]

        for host, port in test_hosts:
            try:
                # Create a socket connection with short timeout
                s = socket.create_connection((host, port), timeout=3)
                s.close()
                logger.info(
                    f"[ConnectionManager] Connection verified via {host}:{port}"
                )
                return True
            except OSError:
                continue

        logger.error("[ConnectionManager] Failed to connect to any test host.")
        return False

    def _process_config(self, config: dict) -> dict:
        """
        Process config for Xray usage.
        1. Ensure log settings.
        2. Resolve domain to IP and patch SNI/Host.
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
        self._configure_dns(new_config)

        return new_config

    def _resolve_domain_to_ip(self, domain: str, timeout: float = 5.0) -> Optional[str]:
        """
        Resolve domain to IP address with timeout.
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

        # Sanitize network (Xray doesn't support 'udp' in streamSettings, it's implied by protocol)
        if network == "udp":
            logger.warning(
                "[ConnectionManager] Removed invalid 'udp' network from streamSettings"
            )
            stream_settings.pop("network", None)
            network = ""  # Reset for subsequent checks

        # Patch network settings
        if network == "ws":
            self._patch_ws_settings(stream_settings, domain)
        elif network == "httpupgrade":
            self._patch_httpupgrade_settings(stream_settings, domain)
        # Note: You might want to add similar patching for Splithttp/Xhttp settings

    def _get_server_object(self, settings: dict) -> Optional[dict]:
        """Extract server object from settings based on protocol."""
        if "vnext" in settings and settings["vnext"]:
            return settings["vnext"][0]
        elif "servers" in settings and settings["servers"]:
            return settings["servers"][0]
        return None

    def _resolve_and_patch_config(self, config: dict):
        """
        Finds the proxy server address, attempts to resolve it to an IP,
        replaces the address with the IP (on success), and sets SNI/Host to the original domain.

        CRITICAL FIX: Implements robust fallback if DNS resolution fails.
        """
        SUPPORTED_PROTOCOLS = ["vless", "vmess", "trojan", "shadowsocks", "hysteria2"]
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

            # Attempt to resolve domain to IP
            ip = self._resolve_domain_to_ip(domain, timeout=DNS_TIMEOUT)

            if ip:
                # SUCCESS: Replace address with IP and patch SNI/Host
                server_obj["address"] = ip
                logger.info(
                    f"[ConnectionManager] Replaced address {domain} with resolved IP {ip}"
                )
            else:
                # FALLBACK: Resolution failed. Keep the original domain and rely on Xray's internal DNS/routing.
                # CRUCIAL: Must still patch stream settings to ensure SNI/Host is correctly set.
                msg = (
                    f"DNS resolution failed for {domain}. "
                    "Keeping domain address and relying on Xray internal DNS/routing."
                )
                logger.warning(f"[ConnectionManager] {msg}")
                # Ensure address remains the domain (in case it was somehow altered)
                server_obj["address"] = domain

            # Patch stream settings with original domain (This is done regardless of IP resolution success,
            # ensuring SNI/Host is correct even if Xray needs to resolve the domain itself).
            try:
                self._patch_stream_settings(outbound, domain)
            except Exception as e:
                logger.error(
                    f"[ConnectionManager] Failed to patch stream settings for {domain}: {e}"
                )

    def _get_socks_port(self, config: dict) -> int:
        """
        Extract SOCKS port from config, overriding with user preference,
        and injects CRITICAL Sniffing settings into Xray's SOCKS inbound.
        """
        # Get user configured port
        user_port = self._config_manager.get_proxy_port()

        # Update the config to listen on this port and inject Sniffing
        for inbound in config.get("inbounds", []):
            if inbound.get("protocol") == "socks":
                inbound["port"] = user_port

                # 👇 CRITICAL FIX: Inject Sniffing to capture the domain name
                # if the traffic comes in as an IP (e.g., if Sing-box resolves it)
                inbound["sniffing"] = {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                    "metadataOnly": False,
                }
                logger.debug("[ConnectionManager] Injected Sniffing settings into Xray SOCKS inbound.")
            # We don't modify http inbound for simplicity unless required
            # elif inbound.get("protocol") == "http":
            #     pass

        return user_port

    def _get_proxy_server_ip(self, config: dict) -> list[str]:
        """
        Extract proxy server IPs/domains from config.
        Returns a list of all server addresses found.
        (Uses the patched addresses, which are now IPs or original domains).
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
            result = subprocess.check_output(
                ["powershell", "-Command", cmd], text=True
            ).strip()
            # Handle multiple gateways if present (take the first one)
            if "\n" in result:
                result = result.split("\n")[0].strip()
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
        if (
            hasattr(self, "_primary_interface_subnet")
            and self._primary_interface_subnet
        ):
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
            (
                interface_name,
                interface_ip,
                subnet,
            ) = NetworkInterfaceDetector.get_primary_interface()

            if not interface_ip:
                logger.warning(
                    "[ConnectionManager] Could not detect primary interface for TUN bypass."
                )
                return

            logger.info(
                f"[ConnectionManager] Detected primary interface: {interface_name} ({interface_ip}, {subnet})"
            )

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

        rules = []
        rules.append(domain_rule)
        rules.append(ip_rule)

        # Inject User Defined Rules (Highest Priority)
        user_rules = self._config_manager.load_routing_rules()

        # Helper to add rule if list not empty
        def add_user_rule(tag, domain_list):
            if domain_list:
                # Separate IP and Domain? Xray field rule accepts both in "domain" or "ip"
                # but it's safer to check format if we want to be strict.
                # However, Xray "domain" field handles plain strings as domain.
                # IPs should ideally go to "ip" field but "domain" *might* not match IP string.
                # For simplicity, we put everything in "domain" field for now,
                # unless user specifies "ip:..." or "geoip:...".
                # Actually, best practice: split them.

                ips = [
                    d for d in domain_list if self._is_ip(d) or d.startswith("geoip:")
                ]
                domains = [d for d in domain_list if d not in ips]

                if domains:
                    rules.insert(
                        0, {"type": "field", "outboundTag": tag, "domain": domains}
                    )
                if ips:
                    rules.insert(0, {"type": "field", "outboundTag": tag, "ip": ips})

        add_user_rule("block", user_rules.get("block", []))
        add_user_rule("proxy", user_rules.get("proxy", []))
        add_user_rule("direct", user_rules.get("direct", []))

        # Assign back
        config["routing"]["rules"] = rules + config["routing"]["rules"]  # Prepend

        direct_rules = len(user_rules.get("direct", []))
        proxy_rules = len(user_rules.get("proxy", []))
        block_rules = len(user_rules.get("block", []))
        total_rules = direct_rules + proxy_rules + block_rules
        logger.info(
            f"[ConnectionManager] Added routing rules. Country: {routing_country}, User Rules: {total_rules}"
        )

    def _is_ip(self, val: str) -> bool:
        """Check if string is IP or standard Xray IP format."""
        if val.startswith("geoip:") or "/" in val:  # CIDR
            return True
        try:
            socket.inet_aton(val)
            return True
        except Exception:
            return False

    def _configure_dns(self, config: dict):
        """Configure DNS based on user settings."""
        dns_config = self._config_manager.load_dns_config()
        if not dns_config:
            # Use default Google/Cloudflare if nothing configured
            # But the 'load_dns_config' returns defaults if empty file, so we are good.
            pass

        servers = []
        for item in dns_config:
            # { "address": "...", "protocol": "doh/udp/tcp", "domains": [] }
            entry = None
            addr = item.get("address", "")
            if not addr:
                continue

            # Format address based on protocol
            # Xray expects:
            # UDP/TCP: "8.8.8.8" or "tcp+local://8.8.8.8"
            # DoH: "https://..."
            # DoT: "tls://..."
            # DoQ: "quic://..."

            proto = item.get("protocol", "udp")

            # Construct server entry string
            if proto == "doh":
                if not addr.startswith("https://"):
                    addr = f"https://{addr}/dns-query"  # Heuristic
            elif proto == "dot":
                if not addr.startswith("tls://"):
                    addr = f"tls://{addr}"
            elif proto == "doq":
                if not addr.startswith("quic://"):
                    addr = f"quic://{addr}"
            elif proto == "tcp":
                if not addr.startswith("tcp+local://"):  # local dns resolution over tcp
                    # Wait, standard TCP dns query to remote? Xray usually infers.
                    # But explicit is: "tcp://8.8.8.8" (not valid standard xray schema?)
                    # Xray: "8.8.8.8" -> UDP.
                    # For TCP: "tcp://8.8.8.8" works in some cores, or "tcp+local://"?
                    # Let's stick to simple "8.8.8.8" for UDP default.
                    pass

            # Create full object if domains specified
            domains = item.get("domains", [])
            if domains:
                entry = {"address": addr, "domains": domains}
                # Check for "expectIPs" or "skipFallback" if needed (Advanced)
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

        logger.info(f"[ConnectionManager] Configured DNS with {len(servers)} servers")
