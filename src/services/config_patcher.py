"""Safe stream setting fallbacks for Xray configuration."""
from loguru import logger

from src.core.constants import (
    CONFIG_NETWORK,
    CONFIG_OUTBOUNDS,
    CONFIG_SETTINGS,
    CONFIG_STREAM_SETTINGS,
    HEADER_HOST,
    NETWORK_HTTPUPGRADE,
    NETWORK_WS,
    NETWORK_XHTTP,
    REALITY_SETTINGS,
    SECURITY_NONE,
    SECURITY_REALITY,
    SECURITY_TLS,
    STREAM_HEADERS,
    STREAM_HOST,
    STREAM_HTTPUPGRADE_SETTINGS,
    STREAM_MODE,
    STREAM_SERVER_NAME,
    STREAM_WS_SETTINGS,
    STREAM_XHTTP_SETTINGS,
    TLS_SETTINGS,
)
from src.services.config_utils import get_server_object, is_ip


class ConfigPatcher:
    """Applies non-destructive stream setting fallbacks (SNI, Host, etc.)."""

    SUPPORTED_PROTOCOLS = ["vless", "vmess", "trojan", "shadowsocks", "hysteria2"]

    def safe_patch(self, config: dict):
        """Apply context-aware fallbacks only if fields are missing."""
        fallback_count = 0
        for outbound in config.get("outbounds", []):
            protocol = outbound.get("protocol")
            if protocol not in self.SUPPORTED_PROTOCOLS:
                continue

            settings = outbound.get(CONFIG_SETTINGS, {})
            server_obj = get_server_object(settings)
            if not server_obj or "address" not in server_obj:
                continue

            domain = server_obj["address"]

            applied = self._apply_stream_fallbacks(outbound, domain)
            if applied:
                fallback_count += 1
        if fallback_count > 0:
            logger.info(f"[ConfigPatcher] Applied safe fallbacks to {fallback_count} outbound(s)")

    def _apply_stream_fallbacks(self, outbound: dict, domain: str) -> bool:
        """Safe fallbacks for stream settings (SNI/Host) if missing."""
        applied = False
        stream_settings = outbound.setdefault(CONFIG_STREAM_SETTINGS, {})
        security = stream_settings.get("security", SECURITY_NONE)
        network = stream_settings.get(CONFIG_NETWORK, "")

        if security in (SECURITY_TLS, SECURITY_REALITY) and security != SECURITY_NONE:
            field = TLS_SETTINGS if security == SECURITY_TLS else REALITY_SETTINGS
            sec_settings = stream_settings.setdefault(field, {})
            if not sec_settings.get(STREAM_SERVER_NAME):
                if not is_ip(domain):
                    sec_settings[STREAM_SERVER_NAME] = domain
                    logger.info(f"[ConfigPatcher] Fallback: Set {field}.serverName = {domain}")
                    applied = True

        if network == NETWORK_WS:
            ws_settings = stream_settings.setdefault(STREAM_WS_SETTINGS, {})
            headers = ws_settings.setdefault(STREAM_HEADERS, {})
            if not headers.get(HEADER_HOST) and not is_ip(domain):
                headers[HEADER_HOST] = domain
                logger.info(f"[ConfigPatcher] Fallback: Set wsSettings.headers.Host = {domain}")
                applied = True
        elif network == NETWORK_HTTPUPGRADE:
            hu_settings = stream_settings.setdefault(STREAM_HTTPUPGRADE_SETTINGS, {})
            if not hu_settings.get(STREAM_HOST) and not is_ip(domain):
                hu_settings[STREAM_HOST] = domain
                logger.info(f"[ConfigPatcher] Fallback: Set httpupgradeSettings.host = {domain}")
                applied = True
        elif network == NETWORK_XHTTP:
            xhttp_settings = stream_settings.setdefault(STREAM_XHTTP_SETTINGS, {})
            if not xhttp_settings.get(STREAM_HOST) and not is_ip(domain):
                xhttp_settings[STREAM_HOST] = domain
                logger.info(f"[ConfigPatcher] Fallback: Set xhttpSettings.host = {domain}")
                applied = True

            if not xhttp_settings.get(STREAM_MODE):
                xhttp_settings[STREAM_MODE] = "packet-up"
                logger.info("[ConfigPatcher] Set xhttpSettings.mode = packet-up for stability")
                applied = True

        return applied
