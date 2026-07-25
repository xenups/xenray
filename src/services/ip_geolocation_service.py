"""IP Geolocation Service - Fetches public exit IP and country metadata."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from src.core.logger import logger

_IP_GEO_CACHE: Dict[str, Tuple[Optional[str], Optional[str]]] = {}


class IPGeolocationService:
    """Service to resolve IP address location data and public exit IPs."""

    @staticmethod
    def fetch_country_info_from_ip(ip: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetch country code and country name from server IP address using ip-api.com and ipapi.co.
        Returns (country_code, country_name).
        """
        if not ip or not isinstance(ip, str) or ip in ("--", "127.0.0.1", "localhost"):
            return None, None

        if ip in _IP_GEO_CACHE:
            return _IP_GEO_CACHE[ip]

        import requests

        # Endpoint 1: ip-api.com
        try:
            response = requests.get(f"http://ip-api.com/json/{ip}?fields=status,countryCode,country", timeout=2)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    code = data.get("countryCode")
                    name = data.get("country")
                    res = (code, name)
                    _IP_GEO_CACHE[ip] = res
                    return res
        except Exception as e:
            logger.debug(f"ip-api.com lookup failed for IP {ip}: {e}")

        # Endpoint 2: ipapi.co fallback
        try:
            response = requests.get(f"https://ipapi.co/{ip}/json/", timeout=2, headers={"User-Agent": "curl/7.68.0"})
            if response.status_code == 200:
                data = response.json()
                code = data.get("country_code")
                name = data.get("country_name")
                if code and name:
                    res = (code, name)
                    _IP_GEO_CACHE[ip] = res
                    return res
        except Exception as e:
            logger.debug(f"ipapi.co lookup failed for IP {ip}: {e}")

        _IP_GEO_CACHE[ip] = (None, None)
        return None, None

    @classmethod
    def resolve_proxy_ports(
        cls, socks_port: Optional[int] = None, http_port: Optional[int] = None
    ) -> Tuple[int, int]:
        """
        Dynamically resolve active SOCKS and HTTP proxy ports from SettingsRepository or parameters.
        Returns (socks_port, http_port).
        """
        if socks_port and socks_port > 0:
            active_socks = socks_port
        else:
            try:
                from src.core.constants import CONFIG_DIR
                from src.repositories.settings_repository import SettingsRepository

                settings = SettingsRepository(CONFIG_DIR)
                active_socks = settings.get_proxy_port()
            except Exception:
                active_socks = 10808

        if http_port and http_port > 0:
            active_http = http_port
        else:
            active_http = active_socks + 4 if active_socks <= 65531 else active_socks + 1

        return active_socks, active_http

    @classmethod
    def _make_proxied_request(
        cls,
        url: str,
        socks_port: Optional[int] = None,
        http_port: Optional[int] = None,
        timeout: float = 2.5,
        headers: Optional[dict] = None,
    ) -> Optional[requests.Response]:
        """Execute request using dynamically resolved HTTP and SOCKS proxy ports."""
        import requests

        resolved_socks, resolved_http = cls.resolve_proxy_ports(socks_port, http_port)

        # Build proxy configs in priority order:
        # 1. HTTP inbound proxy (reliable, lightweight, no PySocks requirement)
        # 2. Direct HTTP proxy on SOCKS port
        # 3. SOCKS5h inbound proxy
        proxy_configs = [
            {
                "http": f"http://127.0.0.1:{resolved_http}",
                "https": f"http://127.0.0.1:{resolved_http}",
            },
            {
                "http": f"http://127.0.0.1:{resolved_socks}",
                "https": f"http://127.0.0.1:{resolved_socks}",
            },
            {
                "http": f"socks5h://127.0.0.1:{resolved_socks}",
                "https": f"socks5h://127.0.0.1:{resolved_socks}",
            },
        ]

        for proxies in proxy_configs:
            try:
                resp = requests.get(url, proxies=proxies, timeout=timeout, headers=headers)
                if resp.status_code == 200:
                    return resp
            except requests.exceptions.InvalidSchema:
                # Missing PySocks — skip SOCKS scheme silently
                continue
            except Exception:
                # Silent fallback on read timeout or refused port
                pass

        # Fallback to direct request (e.g., when TUN mode routes system traffic)
        try:
            resp = requests.get(url, timeout=timeout, headers=headers)
            if resp.status_code == 200:
                return resp
        except Exception:
            pass

        return None

    @classmethod
    def fetch_public_exit_ip(
        cls,
        proxy_port: Optional[int] = None,
        socks_port: Optional[int] = None,
        http_port: Optional[int] = None,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Fetch active public exit location IP, country code, and country name dynamically.
        Supports short timeout (max 2.5s per provider) and returns (exit_ip, country_code, country_name).
        """
        effective_socks = socks_port or proxy_port

        providers = [
            ("https://api.ipify.org?format=json", lambda r: r.json().get("ip")),
            ("http://ip-api.com/json?fields=status,query,countryCode,country", None),
            ("https://ipapi.co/json/", lambda r: r.json().get("ip")),
            ("https://ifconfig.me/ip", lambda r: r.text.strip()),
            ("https://icanhazip.com", lambda r: r.text.strip()),
        ]

        for url, extractor in providers:
            resp = cls._make_proxied_request(
                url,
                socks_port=effective_socks,
                http_port=http_port,
                timeout=2.5,
                headers={"User-Agent": "curl/7.68.0"},
            )
            if not resp or resp.status_code != 200:
                continue

            try:
                if "ip-api.com" in url:
                    data = resp.json()
                    if data.get("status") == "success":
                        return data.get("query"), data.get("countryCode"), data.get("country")
                elif "ipapi.co" in url:
                    data = resp.json()
                    ip = data.get("ip")
                    if ip:
                        return ip, data.get("country_code"), data.get("country_name")
                else:
                    ip = extractor(resp) if extractor else None
                    if ip and isinstance(ip, str) and 7 <= len(ip) <= 45:
                        code, name = cls.fetch_country_info_from_ip(ip)
                        return ip, code, name
            except Exception:
                continue

        return None, None, None

    @classmethod
    def fetch_public_exit_ip_async(
        cls,
        callback: Callable[[Optional[str], Optional[str], Optional[str]], None],
        socks_port: Optional[int] = None,
        http_port: Optional[int] = None,
    ):
        """Fetch exit IP asynchronously in background thread without blocking UI."""
        import threading

        def _worker():
            res = cls.fetch_public_exit_ip(socks_port=socks_port, http_port=http_port)
            if callback:
                try:
                    callback(*res)
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()


# Backward-compatible function aliases
fetch_country_info_from_ip = IPGeolocationService.fetch_country_info_from_ip
fetch_public_exit_ip = IPGeolocationService.fetch_public_exit_ip
