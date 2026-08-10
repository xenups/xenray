"""Self-contained auto-reconnect toggle component for settings."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class AutoReconnectToggleRow(ft.Container):
    """Self-contained auto-reconnect toggle component."""

    def __init__(
        self,
        app_context,
        toast_callback: Callable[[str, str], None],
    ):
        self._app_context = app_context
        self._toast_callback = toast_callback

        is_enabled = app_context.settings.get_auto_reconnect_enabled()
        self._switch = ft.Switch(
            value=is_enabled,
            active_color=ft.Colors.PRIMARY,
            on_change=self._handle_toggle,
        )

        self._sublabel = ft.Text(t("settings.experimental"), size=11, color=ft.Colors.ON_SURFACE_VARIANT)

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.AUTORENEW, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column(
                        [
                            ft.Text(t("settings.auto_reconnect"), weight=ft.FontWeight.W_500),
                            self._sublabel,
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    self._switch,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        )

    def _handle_toggle(self, e):
        """Handle toggle change - coordinates persistence and UI update."""
        enabled = self._switch.value
        self._app_context.settings.set_auto_reconnect_enabled(enabled)

        if enabled:
            self._toast_callback(t("settings.auto_reconnect_enabled"), "success")
        else:
            self._toast_callback(t("settings.auto_reconnect_disabled"), "info")

        try:
            if self.page:
                self.page.update()
        except (RuntimeError, AttributeError):
            pass
