"""Bridge Fetcher Service for obtaining Tor bridges dynamically."""

import json
import os
from typing import List, Optional

import requests

from src.core.constants import TMPDIR
from src.core.logger import logger

# Cache file for bridges
BRIDGES_CACHE_FILE = os.path.join(TMPDIR, "tor_bridges.json")

# Moat API endpoints
MOAT_URL = "https://bridges.torproject.org/moat"

# Fallback built-in bridges (only used if online fetch fails)
FALLBACK_OBFS4_BRIDGES = [
    "obfs4 193.11.166.194:27015 2D82C2E354D531A68469ADA8F3F48F94E1E5FA49 cert=4TLQPJrTSaDffMK7Nbao6LC7G9OW/NHkUwIdjLSS3KYf0Nv4/hMr5MzfpjNNLfAEWQDWtj1 iat-mode=0",
    "obfs4 193.11.166.194:27020 86AC7B8D430DAC4117E9F42C9EAED18133863AAF cert=0Y6hlk5WVaXYS0LFwchqMopKh/CZAx/xnkRsNMn+fUU+LclpVmjOyDGZGMBSW7ktGPEfaw iat-mode=0",
    "obfs4 45.145.95.6:27015 C5B7CD6946E61B3C1F3C0FB6F6ADE8154D247F68 cert=+bGb8AYLzjNTl6I5dDpC8xEQZPZ6PQYMz7CHuKB+lWjLeLJDGQFqPoE5znCCcQPPCdM/EA iat-mode=0",
]

# Fallback Snowflake bridges (official Tor Project configuration)
FALLBACK_SNOWFLAKE_BRIDGES = [
    "snowflake 192.0.2.3:80 2B280B23E1107BB62ABFC40DDCC8824814F80A72 fingerprint=2B280B23E1107BB62ABFC40DDCC8824814F80A72 url=https://snowflake-broker.torproject.net.global.prod.fastly.net/ fronts=www.shazam.com,www.hyatt.com ice=stun:stun.l.google.com:19302,stun:stun.antisip.com:3478,stun:stun.bluesip.net:3478,stun:stun.dus.net:3478,stun:stun.epygi.com:3478,stun:stun.sonetel.com:3478,stun:stun.uls.co.za:3478,stun:stun.voipgate.com:3478,stun:stun.voys.nl:3478 utls-imitate=hellorandomizedalpn",
]


class BridgeFetcher:
    """Service for fetching Tor bridges from various sources."""

    @staticmethod
    def get_bridges(transport_type: str = "obfs4") -> List[str]:
        """
        Get bridges, trying cache first, then online fetch, then fallback.
        
        Args:
            transport_type: Type of bridge transport (obfs4, snowflake, etc.)
            
        Returns:
            List of bridge lines
        """
        # Try cached bridges first
        cached = BridgeFetcher._load_from_cache(transport_type)
        if cached:
            logger.info(f"[BridgeFetcher] Using {len(cached)} cached {transport_type} bridges")
            return cached
        
        # Try fetching fresh bridges
        fresh = BridgeFetcher._fetch_from_moat(transport_type)
        if fresh:
            BridgeFetcher._save_to_cache(transport_type, fresh)
            logger.info(f"[BridgeFetcher] Fetched {len(fresh)} fresh {transport_type} bridges")
            return fresh
        
        # Fallback to built-in bridges
        if transport_type == "obfs4":
            logger.warning("[BridgeFetcher] Using fallback obfs4 bridges")
            return FALLBACK_OBFS4_BRIDGES
        elif transport_type == "snowflake":
            logger.warning("[BridgeFetcher] Using fallback Snowflake bridges")
            return FALLBACK_SNOWFLAKE_BRIDGES
        
        return []

    @staticmethod
    def _fetch_from_moat(transport_type: str) -> Optional[List[str]]:
        """Fetch bridges from the Moat API."""
        try:
            # Step 1: Get challenge (fetch options)
            fetch_response = requests.post(
                f"{MOAT_URL}/fetch",
                json={"type": "client-transports", "supported": [transport_type]},
                headers={"Content-Type": "application/vnd.api+json"},
                timeout=30,
            )
            
            if fetch_response.status_code != 200:
                logger.debug(f"[BridgeFetcher] Moat fetch failed: {fetch_response.status_code}")
                return None
            
            fetch_data = fetch_response.json()
            
            # Extract bridges from response
            if "data" in fetch_data and len(fetch_data["data"]) > 0:
                bridges = fetch_data["data"][0].get("bridges", [])
                if bridges:
                    return bridges
            
            logger.debug(f"[BridgeFetcher] No bridges in Moat response")
            return None
            
        except requests.RequestException as e:
            logger.debug(f"[BridgeFetcher] Moat request failed: {e}")
            return None
        except (KeyError, json.JSONDecodeError) as e:
            logger.debug(f"[BridgeFetcher] Failed to parse Moat response: {e}")
            return None

    @staticmethod
    def _load_from_cache(transport_type: str) -> Optional[List[str]]:
        """Load bridges from cache file."""
        if not os.path.exists(BRIDGES_CACHE_FILE):
            return None
        
        try:
            with open(BRIDGES_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            
            if transport_type in cache:
                # Check if cache is not too old (24 hours)
                import time
                cache_time = cache.get("_timestamp", 0)
                if time.time() - cache_time < 86400:  # 24 hours
                    return cache[transport_type]
            
            return None
        except Exception:
            return None

    @staticmethod
    def _save_to_cache(transport_type: str, bridges: List[str]):
        """Save bridges to cache file."""
        try:
            os.makedirs(os.path.dirname(BRIDGES_CACHE_FILE), exist_ok=True)
            
            cache = {}
            if os.path.exists(BRIDGES_CACHE_FILE):
                try:
                    with open(BRIDGES_CACHE_FILE, "r", encoding="utf-8") as f:
                        cache = json.load(f)
                except Exception:
                    pass
            
            import time
            cache[transport_type] = bridges
            cache["_timestamp"] = time.time()
            
            with open(BRIDGES_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except Exception as e:
            logger.debug(f"[BridgeFetcher] Failed to save cache: {e}")

    @staticmethod
    def clear_cache():
        """Clear the bridge cache."""
        if os.path.exists(BRIDGES_CACHE_FILE):
            try:
                os.remove(BRIDGES_CACHE_FILE)
                logger.info("[BridgeFetcher] Cache cleared")
            except Exception:
                pass
