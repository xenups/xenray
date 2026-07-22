"""
Xray configuration processor service.

Orchestrates Xray configuration processing by delegating
DNS, TUN, and patching responsibilities to specialized classes.
"""

import copy
import os
from typing import Optional

from loguru import logger

from src.core.app_context import AppContext
from src.core.constants import (
    CONFIG_ADDRESS,
    CONFIG_DEST_OVERRIDE,
    CONFIG_DOMAIN_STRATEGY,
    CONFIG_ENABLED,
    CONFIG_INBOUNDS,
    CONFIG_METADATA_ONLY,
    CONFIG_NETWORK,
    CONFIG_OUTBOUNDS,
    CONFIG_PORT,
    CONFIG_PROTOCOL,
    CONFIG_ROUTING,
    CONFIG_RULES,
    CONFIG_SETTINGS,
    CONFIG_SNIFFING,
    CONFIG_STREAM_SETTINGS,
    CONFIG_TAG,
    DOMAIN_ASIS,
    MODE_PROXY,
    MODE_VPN,
    NETWORK_HTTP3,
    NETWORK_QUIC,
    NETWORK_TCP,
    PROTOCOL_HTTP,
    PROTOCOL_HYSTERIA2,
    PROTOCOL_SHADOWSOCKS,
    PROTOCOL_SOCKS,
    PROTOCOL_TROJAN,
    PROTOCOL_VLESS,
    PROTOCOL_VMESS,
    SNIFF_DEST_OVERRIDE,
    XRAY_LOCATION_ASSET,
)
from src.services.config_patcher import ConfigPatcher
from src.services.config_utils import get_server_object, is_ip
from src.services.dns_configurator import DnsConfigurator
from src.services.tun_injector import TunInjector
from src.utils.network_utils import NetworkUtils


class XrayConfigProcessor:
    """
    Orchestrates Xray configuration processing.

    Delegates DNS, TUN injection, and stream patching to
    specialized classes (DnsConfigurator, TunInjector, ConfigPatcher).
    """

    SUPPORTED_PROTOCOLS = [PROTOCOL_VLESS, PROTOCOL_VMESS, PROTOCOL_TROJAN, PROTOCOL_SHADOWSOCKS, PROTOCOL_HYSTERIA2]
    CHAINABLE_PROTOCOLS = {
        PROTOCOL_VLESS,
        PROTOCOL_VMESS,
        PROTOCOL_TROJAN,
        PROTOCOL_SHADOWSOCKS,
        PROTOCOL_SOCKS,
        PROTOCOL_HTTP,
        PROTOCOL_HYSTERIA2,
        "tuic",
        "wireguard",
    }
    DNS_TIMEOUT = 5.0

    def __init__(self, app_context: AppContext):
        self._app_context = app_context
        self._dns_configurator = DnsConfigurator(app_context)
        self._tun_injector = TunInjector(app_context)
        self._config_patcher = ConfigPatcher()

    # ------------------------------------------------------------------
    # Public API — preserved from previous interface
    # ------------------------------------------------------------------

    def process_config(self, config: dict, mode: str = MODE_PROXY) -> dict:
        """
        Process config for Xray usage.

        Args:
            config: Raw configuration
            mode: "proxy" or "vpn" — when "vpn", a native TUN inbound is injected

        Returns:
            Processed configuration
        """
        new_config = copy.deepcopy(config)

        new_config["log"] = {"loglevel": "debug", "access": "", "error": ""}

        os.environ["XRAY_LOCATION_ASSET"] = XRAY_LOCATION_ASSET

        self._ensure_inbounds(new_config)

        self._dns_configurator.configure(new_config)

        self._config_patcher.safe_patch(new_config)

        if mode == MODE_VPN:
            is_quic = self.is_quic_transport(new_config)
            mtu_mode = "quic_safe" if is_quic else "auto"
            optimal_mtu = NetworkUtils.detect_optimal_mtu(mtu_mode=mtu_mode)
            routing_country = self._app_context.settings.get_routing_country()
            routing_rules = self._app_context.routing.load_rules()
            proxy_server_ips = self.get_proxy_server_ip(new_config)
            dns_servers = self._dns_configurator.build_tun_servers()
            self._tun_injector.inject(
                new_config,
                dns_servers=dns_servers,
                mtu=optimal_mtu,
                routing_country=routing_country,
                routing_rules=routing_rules,
                proxy_server_ips=proxy_server_ips,
            )

        return new_config

    def build_chain_config(self, chain_profile: dict) -> tuple[bool, Optional[dict], str]:
        """Build a complete Xray configuration for a chain of servers."""
        try:
            items = chain_profile.get("items", [])
            if not items or len(items) < 2:
                return False, None, "Chain must have at least 2 servers"

            resolved_items = []
            for item in items:
                if isinstance(item, str):
                    profile = self._app_context.get_profile_by_id(item)
                    if profile:
                        resolved_items.append(profile)
                    else:
                        logger.warning(f"Chain item not found: {item}")
                elif isinstance(item, dict):
                    resolved_items.append(item)

            if len(resolved_items) < 2:
                return False, None, "Chain has insufficient valid servers"

            chain_outbounds = []
            for i, node in enumerate(resolved_items):
                node_config = node.get("config", {})
                outbounds = node_config.get(CONFIG_OUTBOUNDS, [])
                proxy_out = next((o for o in outbounds if o.get(CONFIG_PROTOCOL) in self.CHAINABLE_PROTOCOLS), None)

                if not proxy_out:
                    return False, None, f"Node {i+1} ({node.get('name')}) has no valid proxy outbound"

                outbound = copy.deepcopy(proxy_out)
                outbound[CONFIG_TAG] = f"proxy_{i}"
                chain_outbounds.append(outbound)

            for i in range(1, len(chain_outbounds)):
                current = chain_outbounds[i]
                prev_tag = chain_outbounds[i - 1][CONFIG_TAG]

                if CONFIG_STREAM_SETTINGS not in current:
                    current[CONFIG_STREAM_SETTINGS] = {}

                if "sockopt" not in current[CONFIG_STREAM_SETTINGS]:
                    current[CONFIG_STREAM_SETTINGS]["sockopt"] = {}

                current[CONFIG_STREAM_SETTINGS]["sockopt"]["dialerProxy"] = prev_tag

            config = {
                "log": {"loglevel": "info"},
                CONFIG_INBOUNDS: [],
                CONFIG_OUTBOUNDS: chain_outbounds,
                CONFIG_ROUTING: {CONFIG_DOMAIN_STRATEGY: DOMAIN_ASIS, CONFIG_RULES: []},
            }

            return True, config, ""

        except Exception as e:
            return False, None, str(e)

    def validate_config(self, config: dict) -> tuple[bool, str]:
        """Validate Xray configuration structure and values."""
        if not config or not isinstance(config, dict):
            return False, "Config must be a non-empty dictionary"

        if CONFIG_OUTBOUNDS not in config or not isinstance(config[CONFIG_OUTBOUNDS], list):
            return False, "Config must have 'outbounds' list"

        if len(config[CONFIG_OUTBOUNDS]) == 0:
            return False, "At least one outbound is required"

        for idx, outbound in enumerate(config[CONFIG_OUTBOUNDS]):
            if not isinstance(outbound, dict):
                return False, f"Outbound {idx} must be a dictionary"

            protocol = outbound.get(CONFIG_PROTOCOL)
            if not protocol:
                return False, f"Outbound {idx} missing 'protocol'"

            if protocol in self.SUPPORTED_PROTOCOLS:
                settings = outbound.get(CONFIG_SETTINGS, {})
                server_obj = get_server_object(settings)
                if server_obj:
                    port = server_obj.get(CONFIG_PORT)
                    if port and not (1 <= port <= 65535):
                        return False, f"Outbound {idx} has invalid port: {port}"

        if CONFIG_INBOUNDS in config:
            for idx, inbound in enumerate(config[CONFIG_INBOUNDS]):
                port = inbound.get(CONFIG_PORT)
                if port and not (1 <= port <= 65535):
                    return False, f"Inbound {idx} has invalid port: {port}"

        return True, ""

    def get_socks_port(self, config: dict) -> int:
        """Extract SOCKS port from config and inject sniffing settings."""
        user_port = self._app_context.settings.get_proxy_port()

        for inbound in config.get(CONFIG_INBOUNDS, []):
            if inbound.get(CONFIG_PROTOCOL) == PROTOCOL_SOCKS:
                inbound[CONFIG_PORT] = user_port

                inbound[CONFIG_SNIFFING] = {
                    CONFIG_ENABLED: True,
                    CONFIG_DEST_OVERRIDE: list(SNIFF_DEST_OVERRIDE),
                    CONFIG_METADATA_ONLY: False,
                }
                logger.debug("[XrayConfigProcessor] Injected Sniffing settings into Xray SOCKS inbound.")

        return user_port

    def get_proxy_server_ip(self, config: dict) -> list[str]:
        """Extract proxy server IPs/domains from config."""
        addresses = []
        for outbound in config.get(CONFIG_OUTBOUNDS, []):
            if outbound.get(CONFIG_PROTOCOL) in [PROTOCOL_VLESS, PROTOCOL_VMESS, PROTOCOL_TROJAN, PROTOCOL_SHADOWSOCKS]:
                settings = outbound.get(CONFIG_SETTINGS, {})
                if "vnext" in settings:
                    for server in settings["vnext"]:
                        addr = server.get(CONFIG_ADDRESS, "")
                        if addr:
                            addresses.append(addr)
                elif "servers" in settings:
                    for server in settings["servers"]:
                        addr = server.get(CONFIG_ADDRESS, "")
                        if addr:
                            addresses.append(addr)
        return list(set(addresses))

    def is_quic_transport(self, config: dict) -> bool:
        """Detect if QUIC/HTTP3 transport is used."""
        for outbound in config.get(CONFIG_OUTBOUNDS, []):
            stream_settings = outbound.get(CONFIG_STREAM_SETTINGS, {})
            network = stream_settings.get(CONFIG_NETWORK, "")
            if network in [NETWORK_QUIC, NETWORK_HTTP3]:
                return True
        return False

    def get_transport_type(self, config: dict) -> str:
        """Get the transport network type from config."""
        for outbound in config.get(CONFIG_OUTBOUNDS, []):
            protocol = outbound.get(CONFIG_PROTOCOL)
            if protocol in self.SUPPORTED_PROTOCOLS:
                stream_settings = outbound.get(CONFIG_STREAM_SETTINGS, {})
                return stream_settings.get(CONFIG_NETWORK, NETWORK_TCP)
        return ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_inbounds(self, config: dict):
        """Ensure inbounds exist with user's configured ports."""
        user_port = self._app_context.settings.get_proxy_port()

        if not config.get(CONFIG_INBOUNDS):
            config[CONFIG_INBOUNDS] = []

        socks_exists = any(ib.get(CONFIG_PROTOCOL) == PROTOCOL_SOCKS for ib in config[CONFIG_INBOUNDS])
        if not socks_exists:
            config[CONFIG_INBOUNDS].append(
                {
                    CONFIG_TAG: PROTOCOL_SOCKS,
                    CONFIG_PORT: user_port,
                    "listen": "127.0.0.1",
                    CONFIG_PROTOCOL: PROTOCOL_SOCKS,
                    CONFIG_SETTINGS: {"udp": True},
                    CONFIG_SNIFFING: {
                        CONFIG_ENABLED: True,
                        CONFIG_DEST_OVERRIDE: list(SNIFF_DEST_OVERRIDE),
                        CONFIG_METADATA_ONLY: False,
                    },
                }
            )
            logger.info(f"[XrayConfigProcessor] Added SOCKS inbound on port {user_port}")
        else:
            for inbound in config[CONFIG_INBOUNDS]:
                if inbound.get(CONFIG_PROTOCOL) == PROTOCOL_SOCKS:
                    inbound[CONFIG_PORT] = user_port
                    inbound[CONFIG_SNIFFING] = {
                        CONFIG_ENABLED: True,
                        CONFIG_DEST_OVERRIDE: list(SNIFF_DEST_OVERRIDE),
                        CONFIG_METADATA_ONLY: False,
                    }

        http_exists = any(ib.get(CONFIG_PROTOCOL) == PROTOCOL_HTTP for ib in config[CONFIG_INBOUNDS])
        if not http_exists:
            config[CONFIG_INBOUNDS].append(
                {
                    CONFIG_TAG: PROTOCOL_HTTP,
                    CONFIG_PORT: user_port + 4,
                    "listen": "127.0.0.1",
                    CONFIG_PROTOCOL: PROTOCOL_HTTP,
                }
            )
            logger.info(f"[XrayConfigProcessor] Added HTTP inbound on port {user_port + 4}")

    # ------------------------------------------------------------------
    # DISABLED — pre-resolution was breaking ECH / Reality / SNI
    # ------------------------------------------------------------------

    def _add_outbound_dns_entries(self, config: dict):
        """Resolve outbound server domains to IPs (DISABLED — kept for reference)."""
        import socket

        for outbound in config.get(CONFIG_OUTBOUNDS, []):
            protocol = outbound.get(CONFIG_PROTOCOL)
            if protocol not in self.SUPPORTED_PROTOCOLS:
                continue

            settings = outbound.get(CONFIG_SETTINGS, {})
            server_obj = get_server_object(settings)

            if not server_obj or CONFIG_ADDRESS not in server_obj:
                continue

            address = server_obj[CONFIG_ADDRESS]
            if is_ip(address):
                continue

            try:
                _, _, ip_list = socket.gethostbyname_ex(address)

                def is_local_ip(ip_str):
                    parts = ip_str.split(".")
                    if len(parts) != 4:
                        return False
                    try:
                        first = int(parts[0])
                        second = int(parts[1])
                        if first == 10 or first == 127:
                            return True
                        if first == 172 and 16 <= second <= 31:
                            return True
                        if first == 192 and second == 168:
                            return True
                    except ValueError:
                        pass
                    return False

                selected_ip = None
                for ip in ip_list:
                    if not is_local_ip(ip):
                        selected_ip = ip
                        break

                if not selected_ip and ip_list:
                    selected_ip = ip_list[0]

                if len(ip_list) > 1:
                    selected_ip = ip_list[-1]

                if selected_ip:
                    server_obj[CONFIG_ADDRESS] = selected_ip

                logger.info(f"[XrayConfigProcessor] Resolved {address} -> {selected_ip} (replaced in outbound config)")
            except Exception as e:
                logger.warning(f"[XrayConfigProcessor] Failed to resolve {address}: {e}")

    def _resolve_outbound_addresses(self, config: dict):
        """Bootstrap DNS resolution (DISABLED — kept for reference)."""
        import socket

        for outbound in config.get(CONFIG_OUTBOUNDS, []):
            protocol = outbound.get(CONFIG_PROTOCOL)
            if protocol not in self.SUPPORTED_PROTOCOLS:
                continue

            settings = outbound.get(CONFIG_SETTINGS, {})
            server_obj = get_server_object(settings)

            if not server_obj or CONFIG_ADDRESS not in server_obj:
                continue

            address = server_obj[CONFIG_ADDRESS]
            if is_ip(address):
                logger.debug(f"[XrayConfigProcessor] Address {address} is already an IP, skipping resolution")
                continue

            try:
                socket.setdefaulttimeout(5.0)
                resolved_ip = socket.gethostbyname(address)
                server_obj[CONFIG_ADDRESS] = resolved_ip
                logger.info(f"Bootstrap: Resolved {address} -> {resolved_ip}")
                logger.info("All DNS queries will now go through tunnel")
            except (socket.gaierror, socket.timeout, OSError) as e:
                logger.error(f"Failed to resolve {address}: {e}")
                logger.warning("Keeping domain address - may cause DNS issues")
            finally:
                socket.setdefaulttimeout(None)
