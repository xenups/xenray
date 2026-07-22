"""
Legacy Configuration Migration Service.

Handles validation and migration of old Xray configurations.
"""

import copy
from typing import Any, Dict

from loguru import logger

from src.core.constants import (
    CONFIG_ADDRESS,
    CONFIG_NETWORK,
    CONFIG_OUTBOUNDS,
    CONFIG_PROTOCOL,
    CONFIG_SETTINGS,
    CONFIG_STREAM_SETTINGS,
    CONFIG_TAG,
    NETWORK_GRPC,
    NETWORK_H3,
    NETWORK_HTTPUPGRADE,
    NETWORK_QUIC,
    NETWORK_SPLITHTTP,
    NETWORK_TCP,
    NETWORK_WS,
    NETWORK_XHTTP,
    PROTOCOL_HTTP,
    REALITY_SETTINGS,
    SECURITY_NONE,
    SECURITY_REALITY,
    SECURITY_TLS,
    STREAM_HOST,
    STREAM_MODE,
    STREAM_PATH,
    STREAM_SERVER_NAME,
    STREAM_XHTTP_SETTINGS,
    TAG_PROXY,
    TLS_SETTINGS,
)
from src.services.config_utils import get_server_object

# Constants (Mirrored from LinkParser for consistency)
VALID_NETWORKS = {
    NETWORK_TCP,
    NETWORK_WS,
    NETWORK_GRPC,
    PROTOCOL_HTTP,
    NETWORK_HTTPUPGRADE,
    NETWORK_XHTTP,
    NETWORK_SPLITHTTP,
    NETWORK_QUIC,
    NETWORK_H3,
}
VALID_SECURITY = {SECURITY_NONE, SECURITY_TLS, SECURITY_REALITY}
DEFAULT_PATH = "/"
DEFAULT_NETWORK = NETWORK_TCP


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
        for outbound in config.get(CONFIG_OUTBOUNDS, []):
            stream_settings = outbound.get(CONFIG_STREAM_SETTINGS, {})
            network = stream_settings.get(CONFIG_NETWORK)

            if network == NETWORK_SPLITHTTP:
                logger.info("[LegacyConfigService] Migrating 'splithttp' to 'xhttp'")
                stream_settings[CONFIG_NETWORK] = NETWORK_XHTTP
                if "splithttpSettings" in stream_settings:
                    stream_settings[STREAM_XHTTP_SETTINGS] = stream_settings.pop("splithttpSettings")

                # Apply XHTTP stability settings during migration
                xhttp_settings = stream_settings.setdefault(STREAM_XHTTP_SETTINGS, {})

                # Set mode to packet-up for best CDN compatibility
                if not xhttp_settings.get(STREAM_MODE):
                    xhttp_settings[STREAM_MODE] = "packet-up"
                    logger.info("[LegacyConfigService] Set xhttpSettings.mode = packet-up for stability")

                # Add XMUX connection cycling settings
                if "xmux" not in xhttp_settings:
                    xhttp_settings["xmux"] = {
                        "maxConcurrency": "16-32",
                        "hMaxReusableSecs": "1800-3000",
                        "hMaxRequestTimes": "600-900",
                    }
                    logger.info("[LegacyConfigService] Added XMUX settings for connection stability")

    def _ensure_outbound_parameters(self, config: Dict[str, Any]):
        """Ensure critical parameters are present or have safe defaults."""
        for outbound in config.get(CONFIG_OUTBOUNDS, []):
            protocol = outbound.get(CONFIG_PROTOCOL)
            if protocol not in self._xray_processor.SUPPORTED_PROTOCOLS:
                continue

            # Ensure tag
            if CONFIG_TAG not in outbound:
                outbound[CONFIG_TAG] = TAG_PROXY

            stream_settings = outbound.setdefault(CONFIG_STREAM_SETTINGS, {})

            # 1. Validate and Default Network
            network = stream_settings.get(CONFIG_NETWORK)
            if not network or network not in VALID_NETWORKS:
                logger.warning(f"[LegacyConfigService] Invalid network '{network}', defaulting to '{DEFAULT_NETWORK}'")
                stream_settings[CONFIG_NETWORK] = DEFAULT_NETWORK

            # 2. Validate Security (log warning, but don't override - preserve existing behavior)
            security = stream_settings.get("security")
            if security and security not in VALID_SECURITY:
                logger.warning(f"[LegacyConfigService] Unknown security '{security}', preserving as-is")

            # 3. Transport Specific Defaults (Shared Logic)
            self._fill_transport_defaults(outbound)

    def _fill_transport_defaults(self, outbound: Dict[str, Any]):
        """Fill missing transport fields (host, path, sni) from context."""
        stream_settings = outbound.get(CONFIG_STREAM_SETTINGS, {})
        network = stream_settings.get(CONFIG_NETWORK)

        # Get address for default host/sni
        settings = outbound.get(CONFIG_SETTINGS, {})
        server_obj = get_server_object(settings)
        address = server_obj.get(CONFIG_ADDRESS, "") if server_obj else ""

        # Apply defaults based on network type if relevant
        if network in (NETWORK_WS, PROTOCOL_HTTP, NETWORK_HTTPUPGRADE, NETWORK_XHTTP):
            key = f"{network}Settings"
            t_settings = stream_settings.setdefault(key, {})

            # Default path
            if STREAM_PATH not in t_settings:
                t_settings[STREAM_PATH] = DEFAULT_PATH

            # Default host if missing and not an IP (best effort)
            if STREAM_HOST not in t_settings and address:
                t_settings[STREAM_HOST] = address

            # XHTTP-specific: Add stability settings (mode + XMUX)
            if network == NETWORK_XHTTP:
                # Set mode to packet-up for best CDN compatibility
                if not t_settings.get(STREAM_MODE):
                    t_settings[STREAM_MODE] = "packet-up"

                # Add XMUX connection cycling settings
                if "xmux" not in t_settings:
                    t_settings["xmux"] = {
                        "maxConcurrency": "16-32",
                        "hMaxReusableSecs": "1800-3000",
                        "hMaxRequestTimes": "600-900",
                    }

        # Default SNI if security is TLS/Reality and SNI is missing
        security = stream_settings.get("security")
        if security in (SECURITY_TLS, SECURITY_REALITY) and address:
            s_key = TLS_SETTINGS if security == SECURITY_TLS else REALITY_SETTINGS
            sec_settings = stream_settings.setdefault(s_key, {})
            if not sec_settings.get(STREAM_SERVER_NAME):
                sec_settings[STREAM_SERVER_NAME] = address

    def is_legacy(self, config: Dict[str, Any]) -> bool:
        """
        Detect if a configuration is in a legacy format.

        Only detects configs that require actual migration (e.g., splithttp -> xhttp).
        Missing/unknown security values are NOT considered legacy - they should be
        preserved to avoid breaking working configs.

        Args:
            config: Configuration dictionary

        Returns:
            True if it's considered legacy and needs migration
        """
        for outbound in config.get(CONFIG_OUTBOUNDS, []):
            stream_settings = outbound.get(CONFIG_STREAM_SETTINGS, {})
            # Detect splithttp (deprecated, needs migration to xhttp)
            if stream_settings.get(CONFIG_NETWORK) == NETWORK_SPLITHTTP:
                return True
            if "splithttpSettings" in stream_settings:
                return True

        return False
