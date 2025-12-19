"""Subscription Manager."""
import base64
import json
import re
import ssl
import threading
import time
import urllib.request
import uuid
from typing import Callable, List, Optional

from src.core.config_manager import ConfigManager
from src.core.logger import logger
from src.utils.link_parser import LinkParser


class SubscriptionManager:
    """Manages subscription fetching and updating."""

    def __init__(self, config_manager: ConfigManager):
        self._config_manager = config_manager

    def fetch_subscription(self, url: str) -> List[dict]:
        """
        Fetch and parse subscription from URL.
        Returns a list of profile configs.
        """
        try:
            # Create SSL context (unverified to avoid issues with some subscription links)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                # Use utf-8-sig to automatically handle/remove BOM if present
                content = response.read().decode("utf-8-sig")

            return self._parse_subscription_content(content)
        except Exception as e:
            logger.error(f"Failed to fetch subscription {url}: {e}")
            raise e

    def _parse_subscription_content(self, content: str) -> List[dict]:
        """Parse base64, plain text, or JSON subscription content."""
        profiles = []

        # 1. Try parsing as JSON (Handling comments)
        try:
            # Pattern matches: "string" OR //comment OR /* comment */
            pattern = r'("[^"\\]*(?:\\.[^"\\]*)*")|//[^\n]*|/\*[\s\S]*?\*/'

            def replacer(match):
                if match.group(1):
                    return match.group(1)
                return ""

            json_content = re.sub(pattern, replacer, content)
            json_content = re.sub(r",\s*([\]}])", r"\1", json_content)
            json_content = "".join(
                ch
                for ch in json_content
                if ch == "\n" or ch == "\r" or ch == "\t" or ord(ch) >= 32
            )

            # Detect if it's likely JSON before trying to parse (must start with [ or {)
            stripped_json = json_content.strip()
            if stripped_json.startswith("[") or stripped_json.startswith("{"):
                data = json.loads(json_content, strict=False)

                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            name = item.get("remarks", item.get("tag", "Server"))
                            profile_id = str(uuid.uuid4())
                            if "outbounds" in item or "inbounds" in item:
                                profiles.append(
                                    {"id": profile_id, "name": name, "config": item}
                                )
                    if profiles:
                        return profiles
        except Exception:
            # Silence JSON errors as it's common for subscriptions to not be JSON
            pass

        # 2. Base64 / Plain Text Parsing
        decoded = content

        # Check if it's base64 encoded by trying to decode it
        # Real base64 subscriptions usually don't have protocol headers in the encoded blob
        if not any(
            content.strip().startswith(p)
            for p in ["vless://", "vmess://", "trojan://", "hysteria2://"]
        ):
            try:
                # Add padding if needed
                padded_content = content.strip()
                missing_padding = len(padded_content) % 4
                if missing_padding:
                    padded_content += "=" * (4 - missing_padding)

                decoded_bytes = base64.b64decode(padded_content)
                decoded = decoded_bytes.decode("utf-8")
            except Exception:
                # Fallback to original content if not valid base64
                decoded = content

        # Split by newlines and parse each link
        links = decoded.splitlines()
        for link in links:
            link = link.strip()
            # Skip empty lines and metadata/comments starting with #
            if not link or link.startswith("#"):
                continue

            try:
                # Use LinkParser.parse_link which handles multiple protocols
                parsed = LinkParser.parse_link(link)
                if parsed:
                    parsed["id"] = str(uuid.uuid4())
                    profiles.append(parsed)
            except Exception:
                # Silently skip invalid lines in a subscription
                continue

        return profiles

    def update_subscription(self, sub_id: str, callback: Optional[Callable] = None):
        """Update a specific subscription by ID."""

        def _task():
            try:
                subs = self._config_manager.load_subscriptions()
                sub = next((s for s in subs if s["id"] == sub_id), None)
                if not sub:
                    return

                url = sub["url"]
                logger.info(f"Updating subscription: {sub['name']} ({url})")

                profiles = self.fetch_subscription(url)

                # Update subscription with new profiles
                # We store profiles INSIDE the subscription object to keep them grouped
                sub["profiles"] = profiles
                sub["updated_at"] = str(time.time())

                self._config_manager.save_subscription_data(sub)

                if callback:
                    callback(True, f"Updated {len(profiles)} servers")
            except Exception as e:
                logger.error(f"Subscription update failed: {e}")
                if callback:
                    callback(False, str(e))

        threading.Thread(target=_task, daemon=True).start()
