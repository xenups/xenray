"""Settings Repository - Concrete JSON-backed storage for application settings."""

import os
from typing import Optional

from src.core.constants import RECENT_FILES_PATH
from src.repositories.file_utils import atomic_write

# Defaults
DEFAULT_PROXY_PORT = 10805
DEFAULT_HTTP_PORT = 10809


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

    # --- HTTP Proxy Port ---
    def get_http_port(self) -> int:
        val = self._read("http_port.txt")
        try:
            port = int(val)
            return port if 1024 <= port <= 65535 else DEFAULT_HTTP_PORT
        except ValueError:
            return DEFAULT_HTTP_PORT

    def set_http_port(self, port: int) -> None:
        if 1024 <= port <= 65535:
            self._write("http_port.txt", str(port))

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
        val = self._read("routing_country.txt", "ir")
        return val if val in {"ir", "cn", "ru", "none"} else "ir"

    def set_routing_country(self, country_code: Optional[str]) -> None:
        if not country_code or country_code in {"ir", "cn", "ru", "none"}:
            self._write("routing_country.txt", country_code or "")

    # --- Close Preference ---
    def get_remember_close_choice(self) -> bool:
        return self._read("remember_close.txt").lower() == "true"

    def set_remember_close_choice(self, enabled: bool) -> None:
        self._write("remember_close.txt", "true" if enabled else "false")

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

    # --- Cipher Suites (global default for TLS/REALITY) ---
    def get_cipher_suites(self) -> str:
        return self._read("cipher_suites.txt", "")

    def set_cipher_suites(self, value: str) -> None:
        self._write("cipher_suites.txt", value)

    # --- Core Engine (Xray) ---
    def get_core_type(self) -> str:
        """Core engine is strictly locked to Xray in XenRay architecture."""
        return "xray"

    def get_core_engine(self) -> str:
        """Alias for get_core_type(). Always returns 'xray'."""
        return "xray"

    def set_core_type(self, core_type: str) -> None:
        """Core engine selection is locked to xray."""
        self._write("core_type.txt", "xray")

    def set_core_engine(self, core_type: str) -> None:
        """Alias for set_core_type()."""
        self._write("core_type.txt", "xray")

    # --- TUN Engine (Xray TUN / Sing-box TUN) ---
    def get_tun_engine(self) -> str:
        val = self._read("tun_engine.txt", "singbox").lower()
        return val if val in {"xray", "singbox"} else "singbox"

    def set_tun_engine(self, engine: str) -> None:
        if engine in {"xray", "singbox"}:
            self._write("tun_engine.txt", engine)

    # --- LAN Proxy Sharing ---
    def get_allow_lan(self) -> bool:
        """Allow other LAN devices to use XenRay's SOCKS/HTTP proxy endpoints."""
        return self._read("allow_lan.txt").lower() == "true"

    def set_allow_lan(self, enabled: bool) -> None:
        self._write("allow_lan.txt", "true" if enabled else "false")
