"""Configuration Manager."""
import json
import os
import re
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from src.core.constants import (LAST_FILE_PATH, MAX_RECENT_FILES,
                                RECENT_FILES_PATH)


class ConfigManager:
    """Manages application configuration and recent files."""
    
    def __init__(self):
        """Initialize config manager."""
        self._config_dir = os.path.dirname(RECENT_FILES_PATH)
        self._ensure_config_dir()
        self._recent_files = self.get_recent_files()
    
    def _ensure_config_dir(self):
        """Ensure configuration directory exists."""
        os.makedirs(self._config_dir, exist_ok=True)
        
    def load_config(self, file_path: str) -> Tuple[Optional[dict], bool]:
        """
        Load configuration from file.
        Returns: (config_dict, should_remove_from_recent)
        """
        if not os.path.exists(file_path):
            return None, True
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Remove comments
                content = re.sub(r'//.*', '', f.read())
                config = json.loads(content)
                return config, False
        except Exception as e:
            print(f"Error loading config: {e}")
            return None, True

    def validate_config(self, config: dict) -> bool:
        """Validate configuration structure."""
        if not config:
            return False
        # Basic validation - check for outbounds
        return "outbounds" in config

    def get_recent_files(self) -> List[str]:
        """Get list of recent files."""
        if not os.path.exists(RECENT_FILES_PATH):
            return []
            
        try:
            with open(RECENT_FILES_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []

    def add_recent_file(self, file_path: str):
        """Add file to recent list."""
        recent = self.get_recent_files()
        
        if file_path in recent:
            recent.remove(file_path)
            
        recent.insert(0, file_path)
        
        # Limit size
        if len(recent) > MAX_RECENT_FILES:
            recent = recent[:MAX_RECENT_FILES]
            
        self._save_recent_files(recent)
        self.set_last_selected_file(file_path)

    def remove_recent_file(self, file_path: str):
        """Remove file from recent list."""
        recent = self.get_recent_files()
        if file_path in recent:
            recent.remove(file_path)
            self._save_recent_files(recent)

    def _save_recent_files(self, files: List[str]):
        """Save recent files list."""
        try:
            with open(RECENT_FILES_PATH, 'w', encoding='utf-8') as f:
                json.dump(files, f, indent=2)
        except Exception as e:
            print(f"Error saving recent files: {e}")

    def get_last_selected_file(self) -> Optional[str]:
        """Get last selected file path."""
        if not os.path.exists(LAST_FILE_PATH):
            return None
            
        try:
            with open(LAST_FILE_PATH, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except:
            return None

    def set_last_selected_file(self, file_path: str):
        """Set last selected file path."""
        try:
            with open(LAST_FILE_PATH, 'w', encoding='utf-8') as f:
                f.write(file_path)
        except Exception as e:
            print(f"Error saving last file: {e}")

    # --- Profile Management ---
    def load_profiles(self) -> List[dict]:
        """Load saved profiles."""
        profiles_path = os.path.join(self._config_dir, "profiles.json")
        if os.path.exists(profiles_path):
            try:
                with open(profiles_path, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []

    def save_profile(self, name: str, config: dict) -> None:
        """Save a new profile."""
        profiles = self.load_profiles()
        profiles.append({
            "id": str(uuid.uuid4()),
            "name": name,
            "config": config,
            "created_at": str(datetime.now())
        })
        
        profiles_path = os.path.join(self._config_dir, "profiles.json")
        with open(profiles_path, 'w') as f:
            json.dump(profiles, f, indent=2)

    def delete_profile(self, profile_id: str) -> None:
        """Delete a profile by ID."""
        profiles = self.load_profiles()
        profiles = [p for p in profiles if p["id"] != profile_id]
        
        profiles_path = os.path.join(self._config_dir, "profiles.json")
        with open(profiles_path, 'w') as f:
            json.dump(profiles, f, indent=2)

    def get_profile_config(self, profile_id: str) -> Optional[dict]:
        """Get config for a specific profile."""
        profiles = self.load_profiles()
        for p in profiles:
            if p["id"] == profile_id:
                return p["config"]
        return None

    def get_last_selected_profile_id(self) -> Optional[str]:
        """Get last selected profile ID."""
        last_profile_path = os.path.join(self._config_dir, "last_profile.txt")
        if not os.path.exists(last_profile_path):
            return None
        try:
            with open(last_profile_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except:
            return None

    def set_last_selected_profile_id(self, profile_id: str):
        """Set last selected profile ID."""
        last_profile_path = os.path.join(self._config_dir, "last_profile.txt")
        try:
            with open(last_profile_path, 'w', encoding='utf-8') as f:
                f.write(profile_id)
        except Exception as e:
            print(f"Error saving last profile: {e}")

    # --- Proxy Port Management ---
    def get_proxy_port(self) -> int:
        """Get the configured proxy port (default: 10808)."""
        port_path = os.path.join(self._config_dir, "proxy_port.txt")
        if not os.path.exists(port_path):
            return 10808
        try:
            with open(port_path, 'r', encoding='utf-8') as f:
                return int(f.read().strip())
        except:
            return 10808

    def set_proxy_port(self, port: int):
        """Set the proxy port."""
        port_path = os.path.join(self._config_dir, "proxy_port.txt")
        try:
            with open(port_path, 'w', encoding='utf-8') as f:
                f.write(str(port))
        except Exception as e:
            print(f"Error saving proxy port: {e}")

    # --- Routing & DNS ---
    def get_routing_country(self) -> Optional[str]:
        """Get selected country for direct routing (e.g., 'ir', 'cn')."""
        path = os.path.join(self._config_dir, "routing_country.txt")
        if not os.path.exists(path):
            return "ir" # Default to Iran
        try:
            with open(path, 'r', encoding='utf-8') as f:
                val = f.read().strip()
                return val if val else "ir"
        except:
            return "ir"

    def set_routing_country(self, country_code: Optional[str]):
        """Set country for direct routing."""
        path = os.path.join(self._config_dir, "routing_country.txt")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(country_code if country_code else "")
        except Exception as e:
            print(f"Error saving routing country: {e}")

    def get_custom_dns(self) -> str:
        """Get custom DNS servers (comma separated)."""
        path = os.path.join(self._config_dir, "custom_dns.txt")
        if not os.path.exists(path):
            return "8.8.8.8, 1.1.1.1"
        try:
            with open(path, 'r', encoding='utf-8') as f:
                val = f.read().strip()
                return val if val else "8.8.8.8, 1.1.1.1"
        except:
            return "8.8.8.8, 1.1.1.1"

    def set_custom_dns(self, dns_string: str):
        """Set custom DNS servers."""
        path = os.path.join(self._config_dir, "custom_dns.txt")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(dns_string)
        except Exception as e:
            print(f"Error saving custom DNS: {e}")

    def get_connection_mode(self) -> str:
        """Get saved connection mode ('proxy' or 'vpn')."""
        path = os.path.join(self._config_dir, "connection_mode.txt")
        if not os.path.exists(path):
            return "proxy"
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except:
            return "proxy"

    def set_connection_mode(self, mode: str):
        """Set connection mode."""
        path = os.path.join(self._config_dir, "connection_mode.txt")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(mode)
        except Exception as e:
            print(f"Error saving connection mode: {e}")

    def get_routing_country(self) -> str:
        """Get routing country for direct bypass."""
        path = os.path.join(self._config_dir, "routing_country.txt")
        if not os.path.exists(path):
            return "none"
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except:
            return "none"

    def set_routing_country(self, country: str):
        """Set routing country for direct bypass."""
        path = os.path.join(self._config_dir, "routing_country.txt")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(country)
        except Exception as e:
            print(f"Error saving routing country: {e}")

    # --- Theme Management ---
    def get_theme_mode(self) -> str:
        """Get saved theme mode ('dark' or 'light')."""
        path = os.path.join(self._config_dir, "theme_mode.txt")
        if not os.path.exists(path):
            return "dark"
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except:
            return "dark"

    def set_theme_mode(self, mode: str):
        """Set theme mode."""
        path = os.path.join(self._config_dir, "theme_mode.txt")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(mode)
        except Exception as e:
            print(f"Error saving theme mode: {e}")

