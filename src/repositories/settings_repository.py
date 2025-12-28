"""Settings Repository - Concrete JSON-backed storage for application settings."""
import os
from typing import Optional

from src.core.constants import RECENT_FILES_PATH
from src.repositories.file_utils import atomic_write

# Defaults
DEFAULT_PROXY_PORT = 10805
DEFAULT_DNS = "8.8.8.8, 1.1.1.1"


class SettingsRepository:
    """Thin wrapper for settings persistence."""

    def __init__(self, config_dir: str = None):
        self._config_dir = config_dir or os.path.dirname(RECENT_FILES_PATH)
        self._ensure_config_dir()
        self._migrate_old_port()

    def _ensure_config_dir(self) -> None:
        if not os.path.exists(self._config_dir):
            os.makedirs(self._config_dir, exist_ok=True)

    def _migrate_old_port(self) -> None:
        """Migrate old 10808 port to new 10805 default."""
        port_path = os.path.join(self._config_dir, "proxy_port.txt")
        if os.path.exists(port_path):
            try:
                with open(port_path, "r", encoding="utf-8") as f:
                    if f.read().strip() == "10808":
                        atomic_write(port_path, str(DEFAULT_PROXY_PORT))
            except Exception:
                pass

    def _read(self, filename: str, default: str = "") -> str:
        """Read a setting file."""
        path = os.path.join(self._config_dir, filename)
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return default

    def _write(self, filename: str, value: str) -> None:
        """Write a setting file."""
        path = os.path.join(self._config_dir, filename)
        atomic_write(path, value)

    # --- Proxy Port ---
    def get_proxy_port(self) -> int:
        val = self._read("proxy_port.txt")
        try:
            port = int(val)
            return port if 1024 <= port <= 65535 else DEFAULT_PROXY_PORT
        except ValueError:
            return DEFAULT_PROXY_PORT

    def set_proxy_port(self, port: int) -> None:
        if 1024 <= port <= 65535:
            self._write("proxy_port.txt", str(port))

    # --- Connection Mode ---
    def get_connection_mode(self) -> str:
        val = self._read("connection_mode.txt", "vpn")
        return val if val in {"proxy", "vpn"} else "vpn"

    def set_connection_mode(self, mode: str) -> None:
        if mode in {"proxy", "vpn"}:
            self._write("connection_mode.txt", mode)

    # --- Theme ---
    def get_theme_mode(self) -> str:
        val = self._read("theme_mode.txt", "dark")
        return val if val in {"dark", "light"} else "dark"

    def set_theme_mode(self, mode: str) -> None:
        if mode in {"dark", "light"}:
            self._write("theme_mode.txt", mode)

    # --- Language ---
    def get_language(self) -> str:
        val = self._read("language.txt", "en")
        return val if val in {"en", "fa", "zh", "ru"} else "en"

    def set_language(self, lang: str) -> None:
        if lang in {"en", "fa", "zh", "ru"}:
            self._write("language.txt", lang)

    # --- Sort Mode ---
    def get_sort_mode(self) -> str:
        val = self._read("sort_mode.txt", "name_asc")
        return val if val in {"name_asc", "ping_asc", "ping_desc"} else "name_asc"

    def set_sort_mode(self, mode: str) -> None:
        if mode in {"name_asc", "ping_asc", "ping_desc"}:
            self._write("sort_mode.txt", mode)

    # --- Routing Country ---
    def get_routing_country(self) -> str:
        val = self._read("routing_country.txt", "none")
        return val if val in {"ir", "cn", "ru", "none"} else "none"

    def set_routing_country(self, country_code: Optional[str]) -> None:
        if not country_code or country_code in {"ir", "cn", "ru", "none"}:
            self._write("routing_country.txt", country_code or "")

    # --- Custom DNS ---
    def get_custom_dns(self) -> str:
        val = self._read("custom_dns.txt")
        return val if val else DEFAULT_DNS

    def set_custom_dns(self, dns_string: str) -> None:
        if isinstance(dns_string, str):
            self._write("custom_dns.txt", dns_string)

    # --- Close Preference ---
    def get_remember_close_choice(self) -> bool:
        return self._read("remember_close.txt").lower() == "true"

    def set_remember_close_choice(self, enabled: bool) -> None:
        self._write("remember_close.txt", "true" if enabled else "false")

    # --- Startup Preference ---
    def get_startup_enabled(self) -> bool:
        return self._read("startup_enabled.txt").lower() == "true"

    def set_startup_enabled(self, enabled: bool) -> None:
        self._write("startup_enabled.txt", "true" if enabled else "false")

    # --- Auto-Reconnect Preference ---
    def get_auto_reconnect_enabled(self) -> bool:
        val = self._read("auto_reconnect_enabled.txt")
        return val.lower() != "false"  # Default True

    def set_auto_reconnect_enabled(self, enabled: bool) -> None:
        self._write("auto_reconnect_enabled.txt", "true" if enabled else "false")

    # --- Last Selected Profile ---
    def get_last_selected_profile_id(self) -> str | None:
        val = self._read("last_profile.txt")
        return val if val else None

    def set_last_selected_profile_id(self, profile_id: str) -> None:
        if profile_id:
            self._write("last_profile.txt", profile_id)
