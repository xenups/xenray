"""Repository for reading and writing application settings."""

from __future__ import annotations

import os
from typing import Optional

from src.core.constants import DEFAULT_DNS, DEFAULT_PROXY_PORT, DEFAULT_TUN_ENGINE
from src.repositories.file_utils import atomic_write, read_file_safe


class SettingsRepository:
    """Encapsulates settings storage and retrieval."""

    def __init__(self, config_dir: str):
        self._config_dir = config_dir
        os.makedirs(self._config_dir, exist_ok=True)

    def _read(self, filename: str, default: str = "") -> str:
        path = os.path.join(self._config_dir, filename)
        return read_file_safe(path, default)

    def _write(self, filename: str, value: str) -> None:
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
        try:
            p = int(port)
            if 1024 <= p <= 65535:
                self._write("proxy_port.txt", str(p))
        except (ValueError, TypeError):
            pass

    # --- Connection Mode ---
    def get_connection_mode(self) -> str:
        val = self._read("connection_mode.txt", "vpn")
        return val if val in {"proxy", "vpn"} else "vpn"

    def set_connection_mode(self, mode: str) -> None:
        if isinstance(mode, str) and mode in {"proxy", "vpn"}:
            self._write("connection_mode.txt", mode)

    # --- Theme ---
    def get_theme_mode(self) -> str:
        val = self._read("theme_mode.txt", "dark")
        return val if val in {"dark", "light"} else "dark"

    def set_theme_mode(self, mode: str) -> None:
        if isinstance(mode, str) and mode in {"dark", "light"}:
            self._write("theme_mode.txt", mode)

    # --- Language ---
    def get_language(self) -> str:
        val = self._read("language.txt", "en")
        return val if isinstance(val, str) and val in {"en", "fa", "zh", "ru"} else "en"

    def set_language(self, lang: str) -> None:
        if isinstance(lang, str) and lang in {"en", "fa", "zh", "ru"}:
            self._write("language.txt", lang)

    # --- Sort Mode ---
    def get_sort_mode(self) -> str:
        val = self._read("sort_mode.txt", "name_asc")
        return val if val in {"name_asc", "ping_asc", "ping_desc"} else "name_asc"

    def set_sort_mode(self, mode: str) -> None:
        if isinstance(mode, str) and mode in {"name_asc", "ping_asc", "ping_desc"}:
            self._write("sort_mode.txt", mode)

    # --- Routing Country ---
    def get_routing_country(self) -> str:
        val = self._read("routing_country.txt", "none")
        return val if val in {"ir", "cn", "ru", "none"} else "none"

    def set_routing_country(self, country_code: Optional[str]) -> None:
        if not country_code or (isinstance(country_code, str) and country_code in {"ir", "cn", "ru", "none"}):
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
        return val.lower() != "false"

    def set_auto_reconnect_enabled(self, enabled: bool) -> None:
        self._write("auto_reconnect_enabled.txt", "true" if enabled else "false")

    # --- Last Selected Profile ---
    def get_last_selected_profile_id(self) -> str | None:
        val = self._read("last_profile.txt")
        return val if val else None

    def set_last_selected_profile_id(self, profile_id: str) -> None:
        if isinstance(profile_id, str) and profile_id:
            self._write("last_profile.txt", profile_id)

    # --- TUN Engine ---
    def get_tun_engine(self) -> str:
        val = self._read("tun_engine.txt", DEFAULT_TUN_ENGINE)
        return val if val in {"sing-box", "xray"} else DEFAULT_TUN_ENGINE

    def set_tun_engine(self, engine: str) -> None:
        if isinstance(engine, str) and engine in {"sing-box", "xray"}:
            self._write("tun_engine.txt", engine)

    def reset_general_preferences(self) -> None:
        """Reset general preferences to defaults without affecting saved server profiles or last selected profile."""
        self.set_proxy_port(DEFAULT_PROXY_PORT)
        self.set_connection_mode("vpn")
        self.set_routing_country("none")
        self.set_custom_dns(DEFAULT_DNS)
        self.set_tun_engine(DEFAULT_TUN_ENGINE)
