"""ECH (Encrypted Client Hello) list resolution, parsing, caching, and refresh manager."""

from __future__ import annotations

import base64
import json
import re
import time
from typing import Any, Dict, Optional

import requests
from loguru import logger


class EchListManager:
    """
    Manages ECH list discovery, retrieval, caching, and refresh.

    Supports:
    - Raw Base64 ECHConfigList strings.
    - HTTP/HTTPS ECH endpoints serving JSON or raw Base64.
    - DoH (DNS-over-HTTPS) JSON responses containing RFC 9460 HTTPS (type 65) RRs with 'ech' parameter.
    - Cache management with graceful fallback: failed refresh preserves valid cached data.
    """

    DEFAULT_TIMEOUT = 5.0
    DEFAULT_TTL = 3600  # 1 hour

    def __init__(self, session: Optional[requests.Session] = None):
        self._session = session or requests.Session()
        # Key: cache_key (str) -> {"ech_list": str, "timestamp": float, "ttl": int}
        self._cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _cache_key(source_url: str, server_name: Optional[str] = None) -> str:
        s_url = source_url.strip()
        s_name = server_name.strip() if server_name else ""
        return f"{s_url}#{s_name}"

    @staticmethod
    def is_valid_ech_config_list(val: str) -> bool:
        """Validate if a string is a well-formed Base64-encoded ECHConfigList."""
        if not val or not isinstance(val, str):
            return False
        clean = val.strip().replace("\n", "").replace("\r", "")
        try:
            raw = base64.b64decode(clean, validate=True)
            # ECHConfigList in RFC 9444 starts with 2-byte total length prefix
            # followed by at least one ECHConfig (version 2 bytes, length 2 bytes, etc.)
            return len(raw) >= 4
        except Exception:
            return False

    @classmethod
    def parse_ech_response(cls, content: str | bytes, server_name: Optional[str] = None) -> Optional[str]:
        """
        Extract Base64 ECHConfigList from various content formats:
        1. Direct Base64 string
        2. JSON with 'ech' or 'echConfigList' key
        3. DoH JSON with Answer array containing HTTPS (type 65) 'ech=...' data
        4. Text response with 'ech=...' assignment
        """
        if isinstance(content, bytes):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = base64.b64encode(content).decode("ascii")
        else:
            text = content

        text = text.strip()
        if not text:
            return None

        # 1. Direct Base64 check
        if cls.is_valid_ech_config_list(text):
            return text

        # 2. JSON parsing
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                # Standard keys
                for key in ("ech", "echConfigList", "ech_config_list", "echConfig"):
                    val = data.get(key)
                    if isinstance(val, str) and cls.is_valid_ech_config_list(val):
                        return val

                # DoH JSON format (RFC 8484 / Cloudflare / Google DoH)
                answers = data.get("Answer", [])
                if isinstance(answers, list):
                    for ans in answers:
                        if isinstance(ans, dict) and ans.get("type") == 65:  # Type HTTPS
                            ans_data = ans.get("data", "")
                            match = re.search(r"ech=([A-Za-z0-9+/=]+)", ans_data)
                            if match:
                                candidate = match.group(1)
                                if cls.is_valid_ech_config_list(candidate):
                                    return candidate
        except (json.JSONDecodeError, ValueError):
            pass

        # 3. Text regex search for ech=<base64>
        match = re.search(r"ech=([A-Za-z0-9+/=]+)", text)
        if match:
            candidate = match.group(1)
            if cls.is_valid_ech_config_list(candidate):
                return candidate

        return None

    def get_cached(self, source_url: str, server_name: Optional[str] = None) -> Optional[str]:
        """Retrieve unexpired cached ECHConfigList, or None."""
        key = self._cache_key(source_url, server_name)
        entry = self._cache.get(key)
        if not entry:
            return None
        now = time.time()
        if now - entry["timestamp"] > entry["ttl"]:
            return None
        return entry["ech_list"]

    def set_cache(
        self,
        source_url: str,
        ech_list: str,
        server_name: Optional[str] = None,
        ttl: int = DEFAULT_TTL,
    ) -> None:
        """Store an ECHConfigList in cache."""
        key = self._cache_key(source_url, server_name)
        self._cache[key] = {
            "ech_list": ech_list,
            "timestamp": time.time(),
            "ttl": ttl,
        }

    def clear_cache(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def fetch_ech_list(
        self,
        source_url: str,
        server_name: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> str:
        """
        Fetch and parse ECHConfigList from a source URL or return if already valid Base64.

        Raises:
            ValueError: If source is unreachable, times out, or returns invalid/empty ECH data.
        """
        if not source_url or not isinstance(source_url, str):
            raise ValueError("ECH-list source URL must be a non-empty string")

        source_url = source_url.strip()

        # If already a raw Base64 ECHConfigList, return directly
        if self.is_valid_ech_config_list(source_url):
            return source_url

        if not (source_url.startswith("http://") or source_url.startswith("https://")):
            raise ValueError(f"Unsupported ECH-list source URL scheme: {source_url}")

        headers = {
            "Accept": "application/dns-json, application/json, text/plain, */*",
            "User-Agent": "Xenray/ECH-Resolver",
        }

        # If it's a DoH endpoint and server_name is provided, ensure query parameters
        req_url = source_url
        if "/dns-query" in source_url and server_name and "name=" not in source_url:
            separator = "&" if "?" in source_url else "?"
            req_url = f"{source_url}{separator}name={server_name}&type=HTTPS"

        try:
            resp = self._session.get(req_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            content = resp.text
        except requests.exceptions.Timeout as exc:
            raise ValueError(f"ECH-list source timed out after {timeout}s: {source_url}") from exc
        except Exception as exc:
            raise ValueError(f"ECH-list source unreachable: {source_url} ({exc})") from exc

        parsed = self.parse_ech_response(content, server_name=server_name)
        if not parsed:
            raise ValueError(f"Failed to parse valid ECHConfigList from source: {source_url}")

        self.set_cache(source_url, parsed, server_name=server_name)
        logger.info(f"[EchListManager] Successfully resolved ECH list from {source_url}")
        return parsed

    def refresh(
        self,
        source_url: str,
        server_name: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> str:
        """
        Refresh ECHConfigList from source.

        If refresh fails (e.g. source unreachable or invalid response),
        previously valid cached data is PRESERVED and returned.

        Raises:
            ValueError: If refresh fails AND no valid cached data is available.
        """
        key = self._cache_key(source_url, server_name)
        previous_entry = self._cache.get(key)

        try:
            return self.fetch_ech_list(source_url, server_name=server_name, timeout=timeout)
        except Exception as exc:
            if previous_entry and previous_entry.get("ech_list"):
                logger.warning(
                    f"[EchListManager] Failed to refresh ECH list from {source_url} ({exc}); "
                    "retaining previously valid cached data"
                )
                return previous_entry["ech_list"]
            raise ValueError(f"Failed to fetch ECH list from {source_url} and no cached data available: {exc}") from exc


# Global instance for shared caching across Xenray
ech_manager = EchListManager()
