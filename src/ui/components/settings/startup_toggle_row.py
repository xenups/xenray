"""Self-contained OS startup toggle component for settings."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class StartupToggleRow(ft.Container):
    """Self-contained startup toggle component managing state and task scheduling."""

    def __init__(
        self,
        app_context,
        is_registered: bool,
        is_supported: bool,
        on_register: Callable[[], tuple],
        on_unregister: Callable[[], tuple],
        toast_callback: Callable[[str, str], None],
    ):
        self._app_context = app_context
        self._on_register = on_register
        self._on_unregister = on_unregister
        self._toast_callback = toast_callback

        self._switch = ft.Switch(
            value=is_registered,
            active_color=ft.Colors.PRIMARY,
            on_change=self._handle_toggle,
            disabled=not is_supported,
        )

        self._sublabel = ft.Text(
            t("settings.add_to_startup_desc"),
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ROCKET_LAUNCH, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column(
                        [
                            ft.Text(t("settings.add_to_startup"), weight=ft.FontWeight.W_500),
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
        """Handle toggle change - coordinates registration and UI update."""
        enabled = self._switch.value

        if enabled:
            success, _ = self._on_register()
        else:
            success, _ = self._on_unregister()

        if success:
            self._app_context.settings.set_startup_enabled(enabled)
            self._toast_callback(t("settings.startup_saved"), "success")
        else:
            self._switch.value = not enabled
            self._switch.update()
            self._toast_callback(t("settings.startup_error"), "error")

        try:
            if self.page:
                self.page.update()
        except (RuntimeError, AttributeError):
            pass
