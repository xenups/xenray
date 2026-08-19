"""Link Parser Facade — dispatches to protocol-specific parser strategies in src.core.parsers."""

from __future__ import annotations

from typing import Any, Dict

from loguru import logger

from src.core.parsers.base import (
    BOOL_FALSE,
    BOOL_TRUE,
    DEFAULT_ENCRYPTION,
    DEFAULT_FINGERPRINT,
    DEFAULT_NETWORK,
    DEFAULT_PATH,
    DEFAULT_PORT,
    DEFAULT_SECURITY,
    SPLIT_FIELDS,
    SUFFIX_CAMEL_MAP,
    UUID_PATTERN,
    VALID_ENCRYPTION,
    VALID_NETWORKS,
    VALID_SECURITY,
    XHTTP_PARAMS,
    _cast_value,
    _expand_fm_to_params,
    _get_cipher_suites,
    _maybe_split,
    _nest_xhttp_extra,
    _route_fm_params,
    _route_xhttp_params,
    _to_camel,
    _validate_fingerprint,
    build_minimal_config,
)
from src.core.parsers.hysteria2 import Hysteria2Parser
from src.core.parsers.trojan import TrojanParser
from src.core.parsers.vless import VlessParser
from src.core.parsers.vmess import VmessParser


class LinkParser:
    """Unified Facade for parsing and generating proxy configuration links."""

    @staticmethod
    def parse_link(link: str) -> Dict[str, Any]:
        """Parse any supported link type (vless, vmess, trojan, hysteria2)."""
        if not link:
            raise ValueError("Link cannot be empty")

        link = link.strip()
        if link.startswith("vless://"):
            return VlessParser.parse(link)
        elif link.startswith("hysteria2://"):
            return Hysteria2Parser.parse(link)
        elif link.startswith("vmess://"):
            return VmessParser.parse(link)
        elif link.startswith("trojan://"):
            return TrojanParser.parse(link)
        else:
            raise ValueError("Unsupported link protocol")

    @staticmethod
    def parse_vless(link: str) -> Dict[str, Any]:
        """Parse VLESS link into Xray configuration."""
        return VlessParser.parse(link)

    @staticmethod
    def parse_vmess(link: str) -> Dict[str, Any]:
        """Parse VMess link into Xray configuration."""
        return VmessParser.parse(link)

    @staticmethod
    def parse_trojan(link: str) -> Dict[str, Any]:
        """Parse Trojan link into Xray configuration."""
        return TrojanParser.parse(link)

    @staticmethod
    def parse_hysteria2(link: str) -> Dict[str, Any]:
        """Parse Hysteria2 link into Xray configuration."""
        return Hysteria2Parser.parse(link)

    @staticmethod
    def _build_config(outbound: Dict) -> Dict:
        """Helper to wrap outbound in minimal config structure."""
        return build_minimal_config(outbound)

    @staticmethod
    def generate_link(config: dict, name: str) -> str:
        """Generate a shareable link from Xray config."""
        try:
            outbounds = config.get("outbounds", [])
            proxy_out = next((o for o in outbounds if o.get("tag") == "proxy"), None)

            if not proxy_out and outbounds:
                proxy_out = outbounds[0]

            if not proxy_out:
                return ""

            protocol = proxy_out.get("protocol")
            if protocol == "vless":
                return VlessParser.generate(proxy_out, name)
            elif protocol == "vmess":
                return VmessParser.generate(proxy_out, name)
            elif protocol == "trojan":
                return TrojanParser.generate(proxy_out, name)
            elif protocol == "hysteria2":
                return Hysteria2Parser.generate(proxy_out, name)
            else:
                return ""
        except Exception as e:
            logger.error(f"Failed to generate link: {e}")
            return ""

    @staticmethod
    def _generate_vless(outbound: dict, name: str) -> str:
        return VlessParser.generate(outbound, name)

    @staticmethod
    def _generate_vmess(outbound: dict, name: str) -> str:
        return VmessParser.generate(outbound, name)

    @staticmethod
    def _generate_trojan(outbound: dict, name: str) -> str:
        return TrojanParser.generate(outbound, name)

    @staticmethod
    def _generate_hysteria2(outbound: dict, name: str) -> str:
        return Hysteria2Parser.generate(outbound, name)


__all__ = [
    "LinkParser",
    "VlessParser",
    "VmessParser",
    "TrojanParser",
    "Hysteria2Parser",
    "DEFAULT_PORT",
    "DEFAULT_NETWORK",
    "DEFAULT_PATH",
    "DEFAULT_ENCRYPTION",
    "DEFAULT_SECURITY",
    "DEFAULT_FINGERPRINT",
    "VALID_NETWORKS",
    "VALID_SECURITY",
    "VALID_ENCRYPTION",
    "UUID_PATTERN",
    "BOOL_TRUE",
    "BOOL_FALSE",
    "SPLIT_FIELDS",
    "XHTTP_PARAMS",
    "SUFFIX_CAMEL_MAP",
    "_to_camel",
    "_get_cipher_suites",
    "_validate_fingerprint",
    "_nest_xhttp_extra",
    "_cast_value",
    "_maybe_split",
    "_route_fm_params",
    "_expand_fm_to_params",
    "_route_xhttp_params",
    "build_minimal_config",
]
