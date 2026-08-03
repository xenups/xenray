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
from src.services.dns_configurator import DnsConfigurator
from src.services.tun_injector import TunInjector
from src.utils.network_utils import NetworkUtils


class XrayConfigProcessor:
    """
    Orchestrates Xray configuration processing.

    Delegates DNS, TUN injection, and stream patching to
    specialized classes (DnsConfigurator, TunInjector, ConfigPatcher).
    """

    SUPPORTED_PROTOCOLS = [
        PROTOCOL_VLESS,
        PROTOCOL_VMESS,
        PROTOCOL_TROJAN,
        PROTOCOL_SHADOWSOCKS,
        PROTOCOL_HYSTERIA2,
    ]
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

        proxy_server_ips = self.get_proxy_server_ip(new_config)
        routing_rules = None
        if mode == MODE_VPN and hasattr(self._app_context, "routing"):
            routing_rules = self._app_context.routing.load_rules()

        self._dns_configurator.configure(
            new_config,
            mode=mode,
            proxy_server_ips=proxy_server_ips,
            routing_rules=routing_rules,
        )

        default_cipher = self._app_context.settings.get_cipher_suites()
        self._config_patcher.safe_patch(new_config, default_cipher_suites=default_cipher)

        if mode == MODE_VPN:
            is_quic = self.is_quic_transport(new_config)
            mtu_mode = "quic_safe" if is_quic else "auto"
            optimal_mtu = NetworkUtils.detect_optimal_mtu(mtu_mode=mtu_mode)
            routing_country = ""
            if hasattr(self._app_context, "settings"):
                routing_country = self._app_context.settings.get_routing_country()
            if routing_rules is None and hasattr(self._app_context, "routing"):
                routing_rules = self._app_context.routing.load_rules()
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
                proxy_out = next(
                    (o for o in outbounds if o.get(CONFIG_PROTOCOL) in self.CHAINABLE_PROTOCOLS),
                    None,
                )

                if not proxy_out:
                    return (
                        False,
                        None,
                        f"Node {i + 1} ({node.get('name')}) has no valid proxy outbound",
                    )

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
            if outbound.get(CONFIG_PROTOCOL) in [
                PROTOCOL_VLESS,
                PROTOCOL_VMESS,
                PROTOCOL_TROJAN,
                PROTOCOL_SHADOWSOCKS,
            ]:
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

    # DISABLED — pre-resolution was breaking ECH / Reality / SNI
    # (Methods _add_outbound_dns_entries and _resolve_outbound_addresses removed)
