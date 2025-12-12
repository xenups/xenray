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
            # Helper to strip comments while preserving strings
            # Pattern matches: "string" OR //comment OR /* comment */
            # We must preserve strings (group 1) to avoid breaking URLs like https://...
            pattern = r'("[^"\\]*(?:\\.[^"\\]*)*")|//[^\n]*|/\*[\s\S]*?\*/'

            def replacer(match):
                # If group 1 (string) matches, preserve it
                if match.group(1):
                    return match.group(1)
                # Otherwise it's a comment, replace with empty string
                return ""

            json_content = re.sub(pattern, replacer, content)

            # Remove trailing commas (common in JSONC)
            # Matches a comma followed by whitespace and then a closing brace/bracket
            json_content = re.sub(r",\s*([\]}])", r"\1", json_content)

            # Scrub invisible control characters (except common whitespace)
            # This handles weird null bytes or other garbage sometimes found in raw URLs
            json_content = "".join(
                ch
                for ch in json_content
                if ch == "\n" or ch == "\r" or ch == "\t" or ord(ch) >= 32
            )

            # Allow control characters like newlines in strings (strict=False)
            data = json.loads(json_content, strict=False)

            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        # Use 'remarks' or 'tag' or default name
                        name = item.get("remarks", item.get("tag", "Server"))

                        # Generate ID
                        profile_id = str(uuid.uuid4())

                        # If the item looks like a full config (has inbounds/outbounds), use it directly
                        if "outbounds" in item or "inbounds" in item:
                            profiles.append(
                                {"id": profile_id, "name": name, "config": item}
                            )
                        # TODO: Handle simplified JSON formats if needed

                if profiles:
                    return profiles

        except json.JSONDecodeError as e:
            logger.warning(
                f"JSON parsing failed: {e.msg} at line {e.lineno} col {e.colno}"
            )
            # Fallback to Base64/Links
        except Exception as e:
            logger.warning(f"JSON parsing error: {e}")

        # 2. Existing Base64 / Plain Text Parsing

        decoded = content

        # Try base64 decode if it looks like base64
        # Skip if it definitely looks like a protocol link or raw JSON/config
        if (
            not content.startswith("vless://")
            and not content.startswith("vmess://")
            and "outbounds" not in content
        ):
            try:
                # Add padding if needed
                missing_padding = len(content) % 4
                if missing_padding:
                    content += "=" * (4 - missing_padding)

                decoded_bytes = base64.b64decode(content)
                decoded = decoded_bytes.decode("utf-8")
            except Exception:
                # Assuming raw text if decode fails
                pass

        # Split by newlines and parse each link
        links = decoded.splitlines()
        for link in links:
            link = link.strip()
            if not link:
                continue

            try:
                # Initialize name to None
                parsed = None

                if link.startswith("vless://"):
                    parsed = LinkParser.parse_vless(link)
                # Future: Add VMess, etc.

                if parsed:
                    # Assign a unique ID to the profile
                    parsed["id"] = str(uuid.uuid4())
                    profiles.append(parsed)
            except Exception as e:
                logger.warning(
                    f"Skipping invalid link in sub: {link[:20]}... Error: {e}"
                )
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
