"""Configuration Manager."""
import json
import os
import re
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from src.core.constants import LAST_FILE_PATH, MAX_RECENT_FILES, RECENT_FILES_PATH
from src.core.logger import logger

# Validation constants
MIN_PORT = 1024
MAX_PORT = 65535
DEFAULT_PROXY_PORT = 10805
DEFAULT_DNS = "8.8.8.8, 1.1.1.1"
VALID_COUNTRY_CODES = {"ir", "cn", "ru", "none"}
VALID_MODES = {"proxy", "vpn"}
VALID_THEMES = {"dark", "light"}
VALID_LANGUAGES = {"en", "fa", "zh", "ru"}


def _validate_file_path(file_path: str) -> bool:
    """Validate file path to prevent path traversal attacks."""
    if not file_path or not isinstance(file_path, str):
        return False
    # Normalize path and check for path traversal
    normalized = os.path.normpath(file_path)
    # Check for dangerous patterns
    if ".." in normalized or normalized.startswith("/"):
        return False
    return True


def _atomic_write(file_path: str, content: str, mode: str = "w") -> bool:
    """
    Atomically write to a file to prevent corruption.
    Uses a temporary file and rename operation.
    """
    try:
        temp_path = file_path + ".tmp"
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(temp_path, mode, encoding="utf-8") as f:
            f.write(content)
        # Atomic rename (works on both Windows and Unix)
        if os.name == "nt":
            # Windows: use replace which is atomic
            os.replace(temp_path, file_path)
        else:
            # Unix: rename is atomic
            os.rename(temp_path, file_path)
        return True
    except (OSError, IOError) as e:
        logger.error(f"Failed to write file {file_path}: {e}")
        # Clean up temp file if it exists
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        return False


def _atomic_write_json(file_path: str, data: dict) -> bool:
    """Atomically write JSON data to a file."""
    try:
        content = json.dumps(data, indent=2)
        return _atomic_write(file_path, content)
    except (TypeError, ValueError) as e:
        logger.error(f"Failed to serialize JSON for {file_path}: {e}")
        return False


class ConfigManager:
    """Manages application configuration and recent files."""

    def __init__(self):
        """Initialize config manager."""
        self._config_dir = os.path.dirname(RECENT_FILES_PATH)
        self._ensure_config_dir()
        self._recent_files = self.get_recent_files()
        self._migrate_old_port()

    def _migrate_old_port(self) -> None:
        """Migrate old 10808 port to new 10805 default."""
        OLD_PORT = 10808
        port_path = os.path.join(self._config_dir, "proxy_port.txt")
        if os.path.exists(port_path):
            try:
                with open(port_path, "r", encoding="utf-8") as f:
                    port_str = f.read().strip()
                    if port_str == str(OLD_PORT):
                        # Migrate to new default
                        _atomic_write(port_path, str(DEFAULT_PROXY_PORT))
                        logger.info(f"Migrated port from {OLD_PORT} to {DEFAULT_PROXY_PORT}")
            except Exception as e:
                logger.debug(f"Port migration check failed: {e}")

    def _ensure_config_dir(self) -> None:
        """Ensure configuration directory exists."""
        try:
            os.makedirs(self._config_dir, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to create config directory: {e}")
            raise

    def load_config(self, file_path: str) -> Tuple[Optional[dict], bool]:
        """
        Load configuration from file.

        Args:
            file_path: Path to the configuration file

        Returns:
            Tuple of (config_dict, should_remove_from_recent)
            Returns (None, True) if file doesn't exist or is invalid
        """
        if not _validate_file_path(file_path):
            logger.warning(f"Invalid file path: {file_path}")
            return None, True

        if not os.path.exists(file_path):
            return None, True

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Remove comments safely using string-aware regex
                # Pattern matches: "string" OR //comment OR /* comment */
                pattern = r'("[^"\\]*(?:\\.[^"\\]*)*")|//[^\n]*|/\*[\s\S]*?\*/'

                def replacer(match):
                    if match.group(1):
                        return match.group(1)  # Keep strings
                    return ""  # Remove comments

                content = re.sub(pattern, replacer, content)
                config = json.loads(content)
                return config, False
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Error parsing config file {file_path}: {e}")
            return None, True
        except (OSError, IOError) as e:
            logger.error(f"Error reading config file {file_path}: {e}")
            return None, True
        except Exception as e:
            logger.error(f"Unexpected error loading config {file_path}: {e}")
            return None, True

    def validate_config(self, config: dict) -> bool:
        """Validate configuration structure."""
        if not config or not isinstance(config, dict):
            return False
        # Basic validation - check for outbounds
        return "outbounds" in config

    def get_recent_files(self) -> List[str]:
        """Get list of recent files."""
        if not os.path.exists(RECENT_FILES_PATH):
            return []

        try:
            with open(RECENT_FILES_PATH, "r", encoding="utf-8") as f:
                files = json.load(f)
                # Validate that it's a list of strings
                if isinstance(files, list):
                    return [
                        f
                        for f in files
                        if isinstance(f, str) and _validate_file_path(f)
                    ]
                return []
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Error parsing recent files: {e}")
            return []
        except (OSError, IOError) as e:
            logger.error(f"Error reading recent files: {e}")
            return []

    def add_recent_file(self, file_path: str) -> None:
        """Add file to recent list."""
        if not _validate_file_path(file_path):
            logger.warning(f"Invalid file path for recent files: {file_path}")
            return

        recent = self.get_recent_files()

        if file_path in recent:
            recent.remove(file_path)

        recent.insert(0, file_path)

        # Limit size
        if len(recent) > MAX_RECENT_FILES:
            recent = recent[:MAX_RECENT_FILES]

        self._save_recent_files(recent)
        self.set_last_selected_file(file_path)

    def remove_recent_file(self, file_path: str) -> None:
        """Remove file from recent list."""
        if not _validate_file_path(file_path):
            return

        recent = self.get_recent_files()
        if file_path in recent:
            recent.remove(file_path)
            self._save_recent_files(recent)

    def _save_recent_files(self, files: List[str]) -> None:
        """Save recent files list using atomic write."""
        if not _atomic_write_json(RECENT_FILES_PATH, files):
            logger.error("Failed to save recent files")

    def get_last_selected_file(self) -> Optional[str]:
        """Get last selected file path."""
        if not os.path.exists(LAST_FILE_PATH):
            return None

        try:
            with open(LAST_FILE_PATH, "r", encoding="utf-8") as f:
                path = f.read().strip()
                if _validate_file_path(path):
                    return path
                return None
        except (OSError, IOError, UnicodeDecodeError) as e:
            logger.error(f"Error reading last file path: {e}")
            return None

    def set_last_selected_file(self, file_path: str) -> None:
        """Set last selected file path using atomic write."""
        if not _validate_file_path(file_path):
            logger.warning(f"Invalid file path: {file_path}")
            return

        if not _atomic_write(LAST_FILE_PATH, file_path):
            logger.error("Failed to save last selected file")

    # --- Profile Management ---
    def load_profiles(self) -> List[dict]:
        """Load saved profiles."""
        profiles_path = os.path.join(self._config_dir, "profiles.json")
        if not os.path.exists(profiles_path):
            return []
        try:
            with open(profiles_path, "r", encoding="utf-8") as f:
                profiles = json.load(f)
                if isinstance(profiles, list):
                    return profiles
                return []
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Error parsing profiles: {e}")
            return []
        except (OSError, IOError) as e:
            logger.error(f"Error reading profiles: {e}")
            return []

    def save_profile(self, name: str, config: dict) -> None:
        """Save a new profile."""
        if not name or not isinstance(name, str):
            logger.warning("Invalid profile name")
            return
        if not isinstance(config, dict):
            logger.warning("Invalid profile config")
            return

        profiles = self.load_profiles()
        profiles.append(
            {
                "id": str(uuid.uuid4()),
                "name": name,
                "config": config,
                "created_at": str(datetime.now()),
            }
        )

        profiles_path = os.path.join(self._config_dir, "profiles.json")
        if not _atomic_write_json(profiles_path, profiles):
            logger.error("Failed to save profile")

    def update_profile(self, profile_id: str, updates: dict) -> bool:
        """Update an existing profile with new data."""
        if not profile_id:
            return False

        profiles = self.load_profiles()
        updated = False

        for p in profiles:
            if p.get("id") == profile_id:
                p.update(updates)
                updated = True
                break

        if updated:
            profiles_path = os.path.join(self._config_dir, "profiles.json")
            if not _atomic_write_json(profiles_path, profiles):
                logger.error("Failed to save updated profile")
                return False
            return True
        return False

    def delete_profile(self, profile_id: str) -> None:
        """Delete a profile by ID."""
        if not profile_id or not isinstance(profile_id, str):
            return

        profiles = self.load_profiles()
        profiles = [p for p in profiles if p.get("id") != profile_id]

        profiles_path = os.path.join(self._config_dir, "profiles.json")
        if not _atomic_write_json(profiles_path, profiles):
            logger.error("Failed to delete profile")

    # --- Subscription Management ---
    def load_subscriptions(self) -> List[dict]:
        """Load saved subscriptions."""
        subs = self._load_json_list("subscriptions.json")
        dirty = False
        for sub in subs:
            # Ensure "profiles" key exists
            if "profiles" not in sub:
                sub["profiles"] = []
                # Not necessarily dirty, but good to normalize

            if isinstance(sub["profiles"], list):
                for profile in sub["profiles"]:
                    if not profile.get("id"):
                        profile["id"] = str(uuid.uuid4())
                        dirty = True

        if dirty:
            self._save_json_list("subscriptions.json", subs)

        return subs

    def save_subscription(self, name: str, url: str) -> None:
        """Save a new subscription."""
        subs = self.load_subscriptions()
        subs.append(
            {
                "id": str(uuid.uuid4()),
                "name": name,
                "url": url,
                "profiles": [],
                "created_at": str(datetime.now()),
            }
        )
        self._save_json_list("subscriptions.json", subs)

    def save_subscription_data(self, subscription: dict) -> None:
        """Update an existing subscription."""
        subs = self.load_subscriptions()
        for i, sub in enumerate(subs):
            if sub["id"] == subscription["id"]:
                subs[i] = subscription
                break
        self._save_json_list("subscriptions.json", subs)

    def delete_subscription(self, sub_id: str) -> None:
        """Delete a subscription."""
        subs = self.load_subscriptions()
        subs = [s for s in subs if s.get("id") != sub_id]
        self._save_json_list("subscriptions.json", subs)

    def _load_json_list(self, filename: str) -> List[dict]:
        path = os.path.join(self._config_dir, filename)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
            return []

    def _save_json_list(self, filename: str, data: List[dict]) -> bool:
        path = os.path.join(self._config_dir, filename)
        return _atomic_write_json(path, data)

    def get_profile_config(self, profile_id: str) -> Optional[dict]:
        """Get config for a specific profile."""
        if not profile_id:
            return None

        profiles = self.load_profiles()
        for p in profiles:
            if p.get("id") == profile_id:
                return p.get("config")
        return None

    def get_last_selected_profile_id(self) -> Optional[str]:
        """Get last selected profile ID."""
        last_profile_path = os.path.join(self._config_dir, "last_profile.txt")
        if not os.path.exists(last_profile_path):
            return None
        try:
            with open(last_profile_path, "r", encoding="utf-8") as f:
                profile_id = f.read().strip()
                return profile_id if profile_id else None
        except (OSError, IOError, UnicodeDecodeError) as e:
            logger.error(f"Error reading last profile ID: {e}")
            return None

    def set_last_selected_profile_id(self, profile_id: str) -> None:
        """Set last selected profile ID using atomic write."""
        if not profile_id:
            return

        last_profile_path = os.path.join(self._config_dir, "last_profile.txt")
        if not _atomic_write(last_profile_path, profile_id):
            logger.error("Failed to save last profile ID")

    # --- Proxy Port Management ---
    def get_proxy_port(self) -> int:
        """Get the configured proxy port (default: 10805)."""
        port_path = os.path.join(self._config_dir, "proxy_port.txt")
        if not os.path.exists(port_path):
            return DEFAULT_PROXY_PORT
        try:
            with open(port_path, "r", encoding="utf-8") as f:
                port_str = f.read().strip()
                port = int(port_str)
                if MIN_PORT <= port <= MAX_PORT:
                    return port
                logger.warning(
                    f"Invalid port {port}, using default {DEFAULT_PROXY_PORT}"
                )
                return DEFAULT_PROXY_PORT
        except (ValueError, OSError, IOError) as e:
            logger.error(f"Error reading proxy port: {e}")
            return DEFAULT_PROXY_PORT

    def set_proxy_port(self, port: int) -> None:
        """Set the proxy port with validation."""
        if not isinstance(port, int) or not (MIN_PORT <= port <= MAX_PORT):
            raise ValueError(f"Port must be between {MIN_PORT} and {MAX_PORT}")

        port_path = os.path.join(self._config_dir, "proxy_port.txt")
        if not _atomic_write(port_path, str(port)):
            logger.error("Failed to save proxy port")

    # --- Routing & DNS ---
    def get_routing_country(self) -> str:
        """Get selected country for direct routing (e.g., 'ir', 'cn', or 'none')."""
        path = os.path.join(self._config_dir, "routing_country.txt")
        if not os.path.exists(path):
            return "none"  # Default to no routing
        try:
            with open(path, "r", encoding="utf-8") as f:
                val = f.read().strip()
                if val in VALID_COUNTRY_CODES:
                    return val
                return "none"
        except (OSError, IOError, UnicodeDecodeError) as e:
            logger.error(f"Error reading routing country: {e}")
            return "none"

    def set_routing_country(self, country_code: Optional[str]) -> None:
        """Set country for direct routing with validation."""
        if country_code and country_code not in VALID_COUNTRY_CODES:
            logger.warning(f"Invalid country code: {country_code}")
            return

        path = os.path.join(self._config_dir, "routing_country.txt")
        content = country_code if country_code else ""
        if not _atomic_write(path, content):
            logger.error("Failed to save routing country")

    def get_custom_dns(self) -> str:
        """Get custom DNS servers (comma separated)."""
        path = os.path.join(self._config_dir, "custom_dns.txt")
        if not os.path.exists(path):
            return DEFAULT_DNS
        try:
            with open(path, "r", encoding="utf-8") as f:
                val = f.read().strip()
                return val if val else DEFAULT_DNS
        except (OSError, IOError, UnicodeDecodeError) as e:
            logger.error(f"Error reading custom DNS: {e}")
            return DEFAULT_DNS

    def set_custom_dns(self, dns_string: str) -> None:
        """Set custom DNS servers."""
        if not isinstance(dns_string, str):
            logger.warning("Invalid DNS string type")
            return

        path = os.path.join(self._config_dir, "custom_dns.txt")
        if not _atomic_write(path, dns_string):
            logger.error("Failed to save custom DNS")

    def get_connection_mode(self) -> str:
        """Get saved connection mode ('proxy' or 'vpn')."""
        path = os.path.join(self._config_dir, "connection_mode.txt")
        if not os.path.exists(path):
            return "vpn"  # Default to VPN mode for first-time users
        try:
            with open(path, "r", encoding="utf-8") as f:
                mode = f.read().strip()
                if mode in VALID_MODES:
                    return mode
                return "vpn"
        except (OSError, IOError, UnicodeDecodeError) as e:
            logger.error(f"Error reading connection mode: {e}")
            return "vpn"

    def set_connection_mode(self, mode: str) -> None:
        """Set connection mode with validation."""
        if mode not in VALID_MODES:
            raise ValueError(f"Mode must be one of {VALID_MODES}")

        path = os.path.join(self._config_dir, "connection_mode.txt")
        if not _atomic_write(path, mode):
            logger.error("Failed to save connection mode")

    # --- Theme Management ---
    def get_theme_mode(self) -> str:
        """Get saved theme mode ('dark' or 'light')."""
        path = os.path.join(self._config_dir, "theme_mode.txt")
        if not os.path.exists(path):
            return "dark"
        try:
            with open(path, "r", encoding="utf-8") as f:
                theme = f.read().strip()
                if theme in VALID_THEMES:
                    return theme
                return "dark"
        except (OSError, IOError, UnicodeDecodeError) as e:
            logger.error(f"Error reading theme mode: {e}")
            return "dark"

    def set_theme_mode(self, mode: str) -> None:
        """Set theme mode with validation."""
        if mode not in VALID_THEMES:
            raise ValueError(f"Theme must be one of {VALID_THEMES}")

        path = os.path.join(self._config_dir, "theme_mode.txt")
        if not _atomic_write(path, mode):
            logger.error("Failed to save theme mode")

    # --- Sort Management ---
    def get_sort_mode(self) -> str:
        """Get saved sort mode ('name_asc', 'ping_asc', 'ping_desc')."""
        path = os.path.join(self._config_dir, "sort_mode.txt")
        if not os.path.exists(path):
            return "name_asc"
        try:
            with open(path, "r", encoding="utf-8") as f:
                mode = f.read().strip()
                if mode in ["name_asc", "ping_asc", "ping_desc"]:
                    return mode
                return "name_asc"
        except (OSError, IOError, UnicodeDecodeError) as e:
            logger.error(f"Error reading sort mode: {e}")
            return "name_asc"

    def set_sort_mode(self, mode: str) -> None:
        """Set sort mode."""
        valid_modes = {"name_asc", "ping_asc", "ping_desc"}
        if mode not in valid_modes:
            return

        path = os.path.join(self._config_dir, "sort_mode.txt")
        if not _atomic_write(path, mode):
            logger.error("Failed to save sort mode")

    # --- Language Management ---
    def get_language(self) -> str:
        """Get saved language ('en' or 'fa')."""
        path = os.path.join(self._config_dir, "language.txt")
        if not os.path.exists(path):
            return "en"
        try:
            with open(path, "r", encoding="utf-8") as f:
                lang = f.read().strip()
                if lang in VALID_LANGUAGES:
                    return lang
                return "en"
        except (OSError, IOError, UnicodeDecodeError) as e:
            logger.error(f"Error reading language: {e}")
            return "en"

    def set_language(self, lang: str) -> None:
        """Set language with validation."""
        if lang not in VALID_LANGUAGES:
            raise ValueError(f"Language must be one of {VALID_LANGUAGES}")

        path = os.path.join(self._config_dir, "language.txt")
        if not _atomic_write(path, lang):
            logger.error("Failed to save language")

    # --- Close Preference ---
    def get_remember_close_choice(self) -> bool:
        """Get 'Remember Choice' for close dialog (default: False)."""
        path = os.path.join(self._config_dir, "remember_close.txt")
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip().lower() == "true"
        except Exception:
            return False

    def set_remember_close_choice(self, enabled: bool) -> None:
        """Set 'Remember Choice' for close dialog."""
        path = os.path.join(self._config_dir, "remember_close.txt")
        if not _atomic_write(path, "true" if enabled else "false"):
            logger.error("Failed to save remember close choice")

    # --- Routing Rules Persistence ---
    def load_routing_rules(self) -> dict:
        """
        Load routing rules.
        Returns dict with keys: 'direct', 'proxy', 'block'.
        Each value is a list of strings (domains/IPs).
        """
        defaults = {"direct": [], "proxy": [], "block": []}
        return self._load_json_list(
            "routing_rules.json", default_type=dict, default_val=defaults
        )

    def save_routing_rules(self, rules: dict):
        """Save routing rules."""
        self._save_json_list("routing_rules.json", rules)

    def get_routing_toggles(self) -> dict:
        """Get routing toggle states."""
        defaults = {
            "block_udp_443": False,
            "block_ads": False,
            "direct_private_ips": True,
            "direct_local_domains": True,
        }
        return self._load_json_list(
            "routing_toggles.json", default_type=dict, default_val=defaults
        )

    def set_routing_toggle(self, name: str, value: bool) -> None:
        """Set a single routing toggle."""
        toggles = self.get_routing_toggles()
        toggles[name] = value
        self._save_json_list("routing_toggles.json", toggles)

    # --- DNS Config Persistence ---
    def load_dns_config(self) -> list:
        """
        Load DNS configuration.
        Returns list of dicts:
        [{ "address": "...", "protocol": "doh/udp/tcp", "domains": [...] }]
        """
        defaults = [
            {"address": "1.1.1.1", "protocol": "udp", "domains": []},
            {"address": "8.8.8.8", "protocol": "udp", "domains": []},
        ]
        return self._load_json_list(
            "dns_config.json", default_type=list, default_val=defaults
        )

    def save_dns_config(self, dns_list: list):
        """Save DNS configuration."""
        self._save_json_list("dns_config.json", dns_list)

    # --- Internal Helpers ---
    def _load_json_list(self, filename: str, default_type=list, default_val=None):
        if default_val is None:
            default_val = [] if default_type is list else {}

        path = os.path.join(self._config_dir, filename)
        if not os.path.exists(path):
            return default_val
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Validation: ensure loaded data matches expected type (list vs dict)
                if isinstance(data, default_type):
                    return data
                return default_val
        except Exception as e:
            logger.error(f"Failed to load {filename}: {e}")
            return default_val

    def _save_json_list(self, filename: str, data):
        # We use atomic write via _atomic_write_json but we need to pass full path?
        # No, _atomic_write_json takes full path. Use helper logic here.
        path = os.path.join(self._config_dir, filename)
        try:
            _atomic_write_json(path, data)
        except Exception as e:
            logger.error(f"Failed to save {filename}: {e}")
