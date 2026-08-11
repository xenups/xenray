"""Settings Controller - manages settings validation, persistence, and event emissions."""

from __future__ import annotations

from typing import Callable, Optional

from src.core.event_bus import event_bus
from src.core.i18n import t
from src.core.logger import logger


class SettingsController:
    """Controller handling settings validation, repository updates, and pub/sub notifications."""

    def __init__(self, app_context, toast_callback: Optional[Callable[[str, str], None]] = None) -> None:
        self._app_context = app_context
        self._toast_callback = toast_callback

    def _show_toast(self, message: str, message_type: str = "info") -> None:
        if self._toast_callback:
            try:
                self._toast_callback(message, message_type)
            except Exception as e:
                logger.error(f"[SettingsController] Toast callback error: {e}")

    def update_socks_port(self, val: int | str) -> tuple[bool, str]:
        """Validate and persist new SOCKS5 proxy port (1024 - 65535).

        Returns (success: bool, result_or_error: str).
        """
        try:
            port = int(val)
            if 1024 <= port <= 65535:
                if self._app_context and hasattr(self._app_context, "settings"):
                    self._app_context.settings.set_proxy_port(port)
                event_bus.publish("settings_updated", {"setting": "socks_port", "value": port})
                msg = t("settings.port_saved", default=f"SOCKS Port saved: {port}", port=port)
                self._show_toast(msg, "success")
                return True, str(port)
            else:
                err = t("settings.port_invalid_range", default="Port must be between 1024 and 65535")
                self._show_toast(err, "error")
                return False, err
        except (ValueError, TypeError):
            err = t("settings.port_must_be_number", default="Port must be a valid number")
            self._show_toast(err, "error")
            return False, err

    def update_http_port(self, val: int | str) -> tuple[bool, str]:
        """Validate and persist new HTTP proxy port (1024 - 65535).

        Returns (success: bool, result_or_error: str).
        """
        try:
            port = int(val)
            if 1024 <= port <= 65535:
                if self._app_context and hasattr(self._app_context, "settings"):
                    self._app_context.settings.set_http_port(port)
                event_bus.publish("settings_updated", {"setting": "http_port", "value": port})
                msg = t("settings.http_port_saved", default=f"HTTP Proxy Port saved: {port}", port=port)
                self._show_toast(msg, "success")
                return True, str(port)
            else:
                err = t("settings.port_invalid_range", default="Port must be between 1024 and 65535")
                self._show_toast(err, "error")
                return False, err
        except (ValueError, TypeError):
            err = t("settings.port_must_be_number", default="Port must be a valid number")
            self._show_toast(err, "error")
            return False, err

    def update_tun_engine(self, engine: str) -> bool:
        """Persist selected TUN engine (sing-box / xray)."""
        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                self._app_context.settings.set_tun_engine(engine)
            event_bus.publish("settings_updated", {"setting": "tun_engine", "value": engine})
            self._show_toast(t("settings.tun_engine_saved", default=f"TUN Engine set to {engine}"), "success")
            return True
        except Exception as e:
            logger.error(f"[SettingsController] Error setting TUN engine: {e}")
            return False

    def update_routing_country(self, code: str) -> bool:
        """Persist selected routing country code."""
        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                self._app_context.settings.set_routing_country(code)
            event_bus.publish("settings_updated", {"setting": "routing_country", "value": code})
            return True
        except Exception as e:
            logger.error(f"[SettingsController] Error setting routing country: {e}")
            return False

    def update_language(self, code: str) -> bool:
        """Persist selected UI language code."""
        try:
            from src.core.i18n import set_language

            set_language(code)
            if self._app_context and hasattr(self._app_context, "settings"):
                self._app_context.settings.set_language(code)
            event_bus.publish("settings_updated", {"setting": "language", "value": code})
            return True
        except Exception as e:
            logger.error(f"[SettingsController] Error setting language: {e}")
            return False
