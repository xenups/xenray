"""Settings Form Presenter - Form validation, port validation, and settings repository updates."""

from __future__ import annotations

from typing import Any, Callable, Tuple

from src.core.app_context import AppContext
from src.core.i18n import set_language as set_app_language
from src.core.i18n import t
from src.core.types import ConnectionMode


class SettingsFormPresenter:
    """Presenter managing settings validation, state persistence, and language/mode changes."""

    def __init__(self, app_context: AppContext, show_toast: Callable):
        self._app_context = app_context
        self._show_toast = show_toast

    def _extract_str_value(self, val: Any) -> str:
        """Extract string value safely from Flet ControlEvent, dict, or direct value."""
        if hasattr(val, "control") and hasattr(val.control, "value"):
            return str(val.control.value or "")
        elif isinstance(val, str):
            return val
        return str(val) if val is not None else ""

    def save_port(self, port_str: Any) -> Tuple[bool, str]:
        """Validate and save proxy port."""
        raw_val = self._extract_str_value(port_str)
        try:
            port = int(raw_val)
            if 1024 <= port <= 65535:
                self._app_context.settings.set_proxy_port(port)
                self._show_toast(t("settings.port_saved"), "success")
                return True, ""
            else:
                self._show_toast(t("settings.port_invalid"), "error")
                return False, t("settings.port_invalid")
        except ValueError:
            self._show_toast(t("settings.port_invalid"), "error")
            return False, t("settings.port_invalid")

    def save_country(self, country_code: Any):
        """Save direct routing country."""
        code = self._extract_str_value(country_code)
        val = code if code != "none" else ""
        self._app_context.settings.set_routing_country(val)
        self._show_toast(t("settings.country_saved"), "success")

    def save_language(self, lang_code: Any):
        """Change application language."""
        code = self._extract_str_value(lang_code)
        self._app_context.settings.set_language(code)
        set_app_language(code)
        self._show_toast(t("settings.language_saved"), "success")

    def reset_close_preference(self):
        """Reset window close action choice."""
        self._app_context.settings.set_close_action("")
        self._show_toast(t("settings.close_choice_reset"), "info")
