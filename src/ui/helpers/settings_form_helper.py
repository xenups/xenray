"""Settings Form Helper - builds settings input rows and handles settings modifications."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.core.i18n import t
from src.core.types import ConnectionMode
from src.ui.components.settings import (
    AutoReconnectToggleRow,
    CountryDropdownRow,
    LanguageDropdownRow,
    ModeSwitchRow,
    PortInputRow,
    StartupToggleRow,
)
from src.utils.process_utils import ProcessUtils

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class SettingsFormHelper:
    """Helper building settings controls and dispatching port/language/mode changes."""

    def __init__(self, main_window: MainWindow) -> None:
        self._mw = main_window

    def build_mode_switch_row(self) -> ModeSwitchRow:
        is_proxy = self._mw._current_mode == ConnectionMode.PROXY
        return ModeSwitchRow(
            is_proxy=is_proxy,
            on_change=lambda e: self.on_mode_changed(ConnectionMode.PROXY if e.control.value else ConnectionMode.VPN),
        )

    def build_port_row(self) -> PortInputRow:
        return PortInputRow(
            initial_value=self._mw._app_context.settings.get_proxy_port(),
            on_save=lambda val: self.save_port(val),
        )

    def build_country_row(self) -> CountryDropdownRow:
        return CountryDropdownRow(
            current_value=self._mw._app_context.settings.get_routing_country() or "",
            on_change=lambda code: self._mw._app_context.settings.set_routing_country(code),
        )

    def build_language_row(self) -> LanguageDropdownRow:
        return LanguageDropdownRow(
            current_value=self._mw._app_context.settings.get_language() or "en",
            on_change=lambda code: self.change_language(code),
        )

    def build_reconnect_row(self) -> AutoReconnectToggleRow:
        return AutoReconnectToggleRow(
            app_context=self._mw._app_context,
            toast_callback=lambda msg, typ: self._mw._show_toast(msg, typ),
        )

    def build_startup_row(self) -> StartupToggleRow:
        from src.services.task_scheduler import is_supported, is_task_registered, register_task, unregister_task

        return StartupToggleRow(
            app_context=self._mw._app_context,
            is_registered=is_task_registered(),
            is_supported=is_supported(),
            on_register=register_task,
            on_unregister=unregister_task,
            toast_callback=self._mw._show_toast,
        )

    def save_port(self, val: str | int) -> None:
        """Save proxy port setting."""
        try:
            port = int(val) if hasattr(val, "control") else int(val)
            self._mw._app_context.settings.set_proxy_port(port)
            self._mw._show_toast(f"SOCKS Port saved: {port}", "success")
        except (ValueError, TypeError):
            self._mw._show_toast("Invalid port", "error")

    @staticmethod
    def change_language(code: str) -> None:
        """Change application language."""
        from src.core.i18n import set_language

        set_language(code)

    def on_mode_changed(self, mode: ConnectionMode) -> None:
        """Handle connection mode change between VPN and Proxy."""
        if mode == ConnectionMode.VPN and not ProcessUtils.is_admin():
            self._mw._show_toast(t("status.admin_required"), "warning")
            return

        self._mw._current_mode = mode
        self._mw._app_context.settings.set_connection_mode("vpn" if mode == ConnectionMode.VPN else "proxy")
        self._mw._status_display.set_status(t("status.mode_selected", mode=mode.name.title()))
        self._mw._ui_helper.call(lambda: None)

        if self._mw._is_running:
            self._mw._connection_handler.reconnect()
