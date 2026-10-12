"""Safe stream setting fallbacks for Xray configuration."""

from loguru import logger

from src.core.constants import (
    CIPHER_SUITES,
    CONFIG_NETWORK,
    CONFIG_SETTINGS,
    CONFIG_STREAM_SETTINGS,
    HEADER_HOST,
    NETWORK_HTTPUPGRADE,
    NETWORK_MASQUE,
    NETWORK_WS,
    NETWORK_XHTTP,
    PROTOCOL_MASQUE,
    PROTOCOL_WARP,
    PROTOCOL_WIREGUARD,
    REALITY_SETTINGS,
    SECURITY_NONE,
    SECURITY_REALITY,
    SECURITY_TLS,
    STREAM_HEADERS,
    STREAM_HOST,
    STREAM_HTTPUPGRADE_SETTINGS,
    STREAM_MASQUE_SETTINGS,
    STREAM_MODE,
    STREAM_SERVER_NAME,
    STREAM_WS_SETTINGS,
    STREAM_XHTTP_SETTINGS,
    TLS_SETTINGS,
    XHTTP_EXTRA_KEYS,
)
from src.services.core_engines.config_utils import get_server_object, is_ip


class ConfigPatcher:
    """Applies non-destructive stream setting fallbacks (SNI, Host, etc.)."""

    SUPPORTED_PROTOCOLS = [
        "vless",
        "vmess",
        "trojan",
        "shadowsocks",
        "hysteria2",
        "wireguard",
        "warp",
        "masque",
    ]

    def safe_patch(self, config: dict, default_cipher_suites: str = ""):
        """Apply context-aware fallbacks only if fields are missing."""
        fallback_count = 0
        for outbound in config.get("outbounds", []):
            protocol = outbound.get("protocol")
            if protocol not in self.SUPPORTED_PROTOCOLS:
                continue

            warp_applied = self._apply_wireguard_warp_hardening(outbound)
            masque_applied = self._apply_masque_hardening(outbound)

            settings = outbound.get(CONFIG_SETTINGS, {})
            server_obj = get_server_object(settings)
            domain = ""
            if server_obj and "address" in server_obj and isinstance(server_obj["address"], str):
                domain = server_obj["address"]

            applied = False
            if domain:
                applied = self._apply_stream_fallbacks(outbound, domain, default_cipher_suites)
            sockopt_applied = self._apply_sockopt_hardening(outbound)
            mux_applied = self._apply_mux_hardening(outbound)
            if applied or sockopt_applied or mux_applied or warp_applied or masque_applied:
                fallback_count += 1
        if fallback_count > 0:
            logger.info(f"[ConfigPatcher] Applied safe fallbacks/hardening to {fallback_count} outbound(s)")

    def _apply_wireguard_warp_hardening(self, outbound: dict) -> bool:
        """Sanitize WARP / WireGuard outbound settings for Xray v26.10.10.

        In v26.10.10, WARP configurations ignore redundant root-level publicKey
        fields under new parameter schemas where peer public keys belong in the
        peers list.
        """
        protocol = outbound.get("protocol")
        if protocol not in (PROTOCOL_WIREGUARD, PROTOCOL_WARP):
            return False

        applied = False
        settings = outbound.setdefault(CONFIG_SETTINGS, {})

        if "publicKey" in settings:
            settings.pop("publicKey", None)
            logger.info("[ConfigPatcher] Stripped redundant root publicKey in WireGuard/WARP outbound")
            applied = True

        return applied

    def _apply_masque_hardening(self, outbound: dict) -> bool:
        """Configure MASQUE outbound transport & security requirements for Xray v26.10.10.

        MASQUE outbound requires network 'masque' and security 'tls'.
        """
        if outbound.get("protocol") != PROTOCOL_MASQUE:
            stream = outbound.get(CONFIG_STREAM_SETTINGS, {})
            if stream.get(CONFIG_NETWORK) != NETWORK_MASQUE:
                return False

        applied = False
        stream = outbound.setdefault(CONFIG_STREAM_SETTINGS, {})
        if stream.get(CONFIG_NETWORK) != NETWORK_MASQUE:
            stream[CONFIG_NETWORK] = NETWORK_MASQUE
            applied = True
        if stream.get("security") != SECURITY_TLS:
            stream["security"] = SECURITY_TLS
            applied = True

        stream.setdefault(STREAM_MASQUE_SETTINGS, {})

        settings = outbound.get(CONFIG_SETTINGS, {})
        server_obj = get_server_object(settings)
        if server_obj and "address" in server_obj and isinstance(server_obj["address"], str):
            domain = server_obj["address"]
            tls_settings = stream.setdefault(TLS_SETTINGS, {})
            if not tls_settings.get(STREAM_SERVER_NAME) and not is_ip(domain):
                tls_settings[STREAM_SERVER_NAME] = domain
                applied = True

        return applied

    def _apply_mux_hardening(self, outbound: dict) -> bool:
        """Ensure MUX is disabled when Vision flow is active in VLESS.

        xtls-rprx-vision controls flow at the TLS record layer and is incompatible
        with multiplexing. Setting mux.enabled = False prevents core runtime panics.
        """
        if outbound.get("protocol") != "vless":
            return False
        settings = outbound.get(CONFIG_SETTINGS, {})
        for server in settings.get("vnext", []):
            for user in server.get("users", []):
                flow = user.get("flow", "")
                if "vision" in flow:
                    mux = outbound.setdefault("mux", {})
                    if mux.get("enabled") is not False:
                        mux["enabled"] = False
                        logger.info("[ConfigPatcher] Disabled MUX for VLESS Reality/Vision outbound")
                        return True
        return False

    def _apply_sockopt_hardening(self, outbound: dict) -> bool:
        """Inject Windows-safe TCP keep-alive settings into streamSettings.sockopt.

        Tuned for Winsock 10-retry kernel realities: 10s idle + (10 * 3s) = 40s kernel drop.
        """
        applied = False
        stream_settings = outbound.setdefault(CONFIG_STREAM_SETTINGS, {})
        sockopt = stream_settings.setdefault("sockopt", {})
        if "tcpKeepAliveInterval" not in sockopt:
            sockopt["tcpKeepAliveInterval"] = 3
            applied = True
        if "tcpKeepAliveIdle" not in sockopt:
            sockopt["tcpKeepAliveIdle"] = 10
            applied = True
        if "tcpNoDelay" not in sockopt:
            sockopt["tcpNoDelay"] = True
            applied = True
        return applied

    def _apply_stream_fallbacks(self, outbound: dict, domain: str, default_cipher_suites: str = "") -> bool:
        """Safe fallbacks for stream settings (SNI/Host) if missing."""
        applied = False
        stream_settings = outbound.setdefault(CONFIG_STREAM_SETTINGS, {})
        security = stream_settings.get("security", SECURITY_NONE)
        network = stream_settings.get(CONFIG_NETWORK, "")

        if security in (SECURITY_TLS, SECURITY_REALITY) and security != SECURITY_NONE:
            field = TLS_SETTINGS if security == SECURITY_TLS else REALITY_SETTINGS
            sec_settings = stream_settings.setdefault(field, {})
            # Sanitize legacy shortIds -> shortId for outbound client REALITY config
            if field == REALITY_SETTINGS and "shortIds" in sec_settings:
                legacy_sids = sec_settings.pop("shortIds")
                if not sec_settings.get("shortId"):
                    if isinstance(legacy_sids, list) and legacy_sids:
                        sec_settings["shortId"] = str(legacy_sids[0]).strip()
                    elif isinstance(legacy_sids, str) and legacy_sids:
                        sec_settings["shortId"] = legacy_sids.split(",")[0].strip()
                logger.info(
                    f"[ConfigPatcher] Sanitized realitySettings.shortIds -> shortId: {sec_settings.get('shortId', '')}"
                )
                applied = True
            if not sec_settings.get(STREAM_SERVER_NAME):
                if not is_ip(domain):
                    sec_settings[STREAM_SERVER_NAME] = domain
                    logger.info(f"[ConfigPatcher] Fallback: Set {field}.serverName = {domain}")
                    applied = True
            if default_cipher_suites and not sec_settings.get(CIPHER_SUITES):
                sec_settings[CIPHER_SUITES] = default_cipher_suites
                logger.info(f"[ConfigPatcher] Fallback: Set {field}.cipherSuites = {default_cipher_suites}")
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

            # Migrate root-level advanced fields into the extra dict
            extra = xhttp_settings.get("extra")
            if not isinstance(extra, dict):
                extra = {}
            for key in list(xhttp_settings.keys()):
                if key in XHTTP_EXTRA_KEYS:
                    extra[key] = xhttp_settings.pop(key)
                    logger.info(f"[ConfigPatcher] Migrated xhttpSettings.{key} into extra dict")
                    applied = True
            if extra:
                xhttp_settings["extra"] = extra

            if not xhttp_settings.get(STREAM_HOST) and not is_ip(domain):
                xhttp_settings[STREAM_HOST] = domain
                logger.info(f"[ConfigPatcher] Fallback: Set xhttpSettings.host = {domain}")
                applied = True

            if not xhttp_settings.get(STREAM_MODE):
                xhttp_settings[STREAM_MODE] = "packet-up"
                logger.info("[ConfigPatcher] Set xhttpSettings.mode = packet-up for stability")
                applied = True
        elif network == NETWORK_MASQUE:
            stream_settings.setdefault(STREAM_MASQUE_SETTINGS, {})
            if stream_settings.get("security") != SECURITY_TLS:
                stream_settings["security"] = SECURITY_TLS
                applied = True

        return applied
