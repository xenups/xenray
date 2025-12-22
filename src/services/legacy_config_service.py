"""
Legacy Configuration Migration Service.

Handles validation and migration of old Xray configurations.
"""

import copy
from typing import Any, Dict

from loguru import logger


# Constants (Mirrored from LinkParser for consistency)
VALID_NETWORKS = {
    "tcp",
    "ws",
    "grpc",
    "http",
    "httpupgrade",
    "xhttp",
    "splithttp",
    "quic",
    "h3",
}
VALID_SECURITY = {"none", "tls", "reality"}
DEFAULT_PATH = "/"
DEFAULT_NETWORK = "tcp"


class LegacyConfigService:
    """Service to validate and migrate legacy configurations."""

    def __init__(self, xray_processor):
        """
        Initialize the service.

        Args:
            xray_processor: Instance of XrayConfigProcessor
        """
        self._xray_processor = xray_processor

    def migrate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate a legacy configuration to the new format.

        Args:
            config: The original configuration dictionary

        Returns:
            The migrated configuration dictionary
        """
        new_config = copy.deepcopy(config)

        # 1. Migrate network types: splithttp -> xhttp
        self._migrate_transports(new_config)

        # 2. Ensure all outbounds follow the new format and have valid defaults
        self._ensure_outbound_parameters(new_config)

        return new_config

    def _migrate_transports(self, config: Dict[str, Any]):
        """Migrate deprecated transport types (e.g., splithttp -> xhttp)."""
        for outbound in config.get("outbounds", []):
            stream_settings = outbound.get("streamSettings", {})
            network = stream_settings.get("network")

            if network == "splithttp":
                logger.info("[LegacyConfigService] Migrating 'splithttp' to 'xhttp'")
                stream_settings["network"] = "xhttp"
                if "splithttpSettings" in stream_settings:
                    stream_settings["xhttpSettings"] = stream_settings.pop("splithttpSettings")

    def _ensure_outbound_parameters(self, config: Dict[str, Any]):
        """Ensure critical parameters are present or have safe defaults."""
        for outbound in config.get("outbounds", []):
            protocol = outbound.get("protocol")
            if protocol not in self._xray_processor.SUPPORTED_PROTOCOLS:
                continue

            # Ensure tag
            if "tag" not in outbound:
                outbound["tag"] = "proxy"

            stream_settings = outbound.setdefault("streamSettings", {})

            # 1. Validate and Default Network
            network = stream_settings.get("network")
            if not network or network not in VALID_NETWORKS:
                logger.warning(f"[LegacyConfigService] Invalid network '{network}', defaulting to '{DEFAULT_NETWORK}'")
                stream_settings["network"] = DEFAULT_NETWORK

            # 2. Validate and Default Security
            security = stream_settings.get("security")
            if not security or security not in VALID_SECURITY:
                # Default "none" is safest. TLS needs certificates/SNI.
                logger.warning(f"[LegacyConfigService] Invalid security '{security}', defaulting to 'none'")
                stream_settings["security"] = "none"

            # 3. Transport Specific Defaults (Shared Logic)
            self._fill_transport_defaults(outbound)

    def _fill_transport_defaults(self, outbound: Dict[str, Any]):
        """Fill missing transport fields (host, path, sni) from context."""
        stream_settings = outbound.get("streamSettings", {})
        network = stream_settings.get("network")

        # Get address for default host/sni
        settings = outbound.get("settings", {})
        server_obj = self._xray_processor._get_server_object(settings)
        address = server_obj.get("address", "") if server_obj else ""

        # Apply defaults based on network type if relevant
        if network in ("ws", "http", "httpupgrade", "xhttp"):
            key = f"{network}Settings"
            t_settings = stream_settings.setdefault(key, {})

            # Default path
            if "path" not in t_settings:
                t_settings["path"] = DEFAULT_PATH

            # Default host if missing and not an IP (best effort)
            if "host" not in t_settings and address:
                t_settings["host"] = address

        # Default SNI if security is TLS/Reality and SNI is missing
        security = stream_settings.get("security")
        if security in ("tls", "reality") and address:
            s_key = "tlsSettings" if security == "tls" else "realitySettings"
            sec_settings = stream_settings.setdefault(s_key, {})
            if not sec_settings.get("serverName"):
                sec_settings["serverName"] = address

    def is_legacy(self, config: Dict[str, Any]) -> bool:
        """
        Detect if a configuration is in a legacy format.

        Args:
            config: Configuration dictionary

        Returns:
            True if it's considered legacy
        """
        for outbound in config.get("outbounds", []):
            stream_settings = outbound.get("streamSettings", {})
            # Detect splithttp
            if stream_settings.get("network") == "splithttp":
                return True
            if "splithttpSettings" in stream_settings:
                return True

            # Detect missing mandatory security field or invalid one
            if "security" not in stream_settings or stream_settings["security"] not in VALID_SECURITY:
                return True

        return False
