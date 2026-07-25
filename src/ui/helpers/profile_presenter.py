"""Profile Presenter - Formats and extracts display-ready metadata from profile objects."""

from __future__ import annotations

import re
import socket
from typing import Dict, Optional, Tuple

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
        """Resolve domain address to numerical IP if possible, or return raw address."""
        if not raw_addr:
            return "--"

        if is_ip(raw_addr):
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

        # Outbound public exit IP vs Config host address
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

        # Saved latency
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

        # Geolocation fallback
        country_code = profile.get("country_code", "")
        country_name = profile.get("country_name", "")

        if not country_code and info["server_ip"] and is_ip(info["server_ip"]):
            from src.utils.country_flags import fetch_country_info_from_ip

            geo_code, geo_name = fetch_country_info_from_ip(info["server_ip"])
            if geo_code:
                country_code = geo_code
                profile["country_code"] = geo_code
            if geo_name:
                country_name = geo_name
                profile["country_name"] = geo_name

        info["country_code"] = country_code
        info["country_name"] = country_name

        return info
