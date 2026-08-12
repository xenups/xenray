"""Profile Presenter - Formats and extracts display-ready metadata from profile objects."""

from __future__ import annotations

import re
import socket
from typing import Dict, Optional

from src.core.i18n import t
from src.services.config_utils import get_server_object, is_ip

_DNS_CACHE: Dict[str, str] = {}


class ProfilePresenter:
    """
    Extracts display information (protocol, encryption, latency, IP, country)
    from raw server profile dictionary objects.
    """

    @staticmethod
    def resolve_server_ip(raw_addr: str) -> str:
        """Resolve domain address to numerical IP from cache, otherwise return raw address.

        Non-blocking: the real DNS lookup is deferred to a background thread via
        :meth:`resolve_server_ip_blocking`, so this NEVER blocks the Flet event loop.
        """
        if not raw_addr:
            return "--"

        if is_ip(raw_addr):
            return raw_addr

        return _DNS_CACHE.get(raw_addr, raw_addr)

    @staticmethod
    def resolve_server_ip_blocking(raw_addr: str) -> str:
        """Blocking DNS resolution. MUST only be called from a background thread."""
        if not raw_addr or is_ip(raw_addr):
            return raw_addr

        if raw_addr in _DNS_CACHE:
            return _DNS_CACHE[raw_addr]

        try:
            resolved = socket.gethostbyname(raw_addr)
            _DNS_CACHE[raw_addr] = resolved
            return resolved
        except Exception:
            return raw_addr

    @classmethod
    def extract_profile_info(cls, profile: Optional[dict]) -> dict:
        """Extract protocol, encryption, latency, server IP, and location from profile."""
        info = {
            "protocol": "Xray / VLESS",
            "encryption": "",
            "latency": "--",
            "server_ip": "--",
            "country_code": "",
            "country_name": "",
        }

        if not profile:
            return info

        config = profile.get("config") or {}
        outbounds = config.get("outbounds") if isinstance(config, dict) else []
        if outbounds:
            ob = outbounds[0]
            proto = (ob.get("protocol") or "").upper()
            if proto:
                info["protocol"] = f"Xray / {proto}"

            stream = ob.get("streamSettings") or {}
            security = stream.get("security", "")
            if security:
                info["encryption"] = security.upper()
            elif proto == "shadowsocks":
                ss_settings = ob.get("settings", {}).get("servers", [{}])[0]
                method = ss_settings.get("method", "")
                info["encryption"] = method.upper() if method else "AES-256-GCM"
            elif proto in ("vless", "vmess"):
                info["encryption"] = "none"

        exit_ip = profile.get("exit_ip") or profile.get("public_ip")
        if exit_ip:
            info["server_ip"] = exit_ip
        else:
            raw_addr = profile.get("address") or profile.get("server") or profile.get("host")
            if not raw_addr:
                config = profile.get("config") or {}
                raw_addr = config.get("address", "")
                if not raw_addr and outbounds:
                    ob = outbounds[0]
                    settings = ob.get("settings", {}) if isinstance(ob, dict) else {}
                    srv_obj = get_server_object(settings) if isinstance(settings, dict) else None
                    if srv_obj and isinstance(srv_obj, dict):
                        raw_addr = srv_obj.get("address", "")

            info["server_ip"] = cls.resolve_server_ip(raw_addr)

        last_val = profile.get("last_latency_val")
        last_str = profile.get("last_latency")
        if last_val is not None:
            info["latency"] = t("connection.latency_ms", value=last_val)
        elif last_str:
            match = re.search(r"(\d+)", str(last_str))
            if match:
                info["latency"] = t("connection.latency_ms", value=int(match.group(1)))
            else:
                info["latency"] = str(last_str)

        country_code = profile.get("country_code", "")
        country_name = profile.get("country_name", "")

        if not country_code and profile.get("name"):
            from src.utils.country_flags import extract_country_code_from_name

            name_cc = extract_country_code_from_name(profile["name"])
            if name_cc:
                country_code = name_cc
                profile["country_code"] = name_cc

        info["country_code"] = country_code
        info["country_name"] = country_name

        return info
