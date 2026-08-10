"""Self-contained LAN proxy sharing toggle component for settings."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class LanShareToggleRow(ft.Container):
    """Self-contained LAN proxy sharing toggle component."""

    def __init__(
        self,
        app_context,
        toast_callback: Callable[[str, str], None],
    ):
        self._app_context = app_context
        self._toast_callback = toast_callback

        is_enabled = app_context.settings.get_allow_lan()
        self._switch = ft.Switch(
            value=is_enabled,
            active_color=ft.Colors.PRIMARY,
            on_change=self._handle_toggle,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.LAN, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column(
                        [
                            ft.Text(t("settings.allow_lan"), weight=ft.FontWeight.W_500),
                            ft.Text(
                                t("settings.allow_lan_desc"),
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
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
        """Persist the setting and manage the firewall rule."""
        enabled = self._switch.value
        self._app_context.settings.set_allow_lan(enabled)

        from src.utils.firewall_manager import FirewallManager

        if enabled:
            port = self._app_context.settings.get_proxy_port()
            FirewallManager.add_lan_firewall_rule([port, port + 4])
            self._toast_callback(t("settings.lan_enabled"), "success")
        else:
            FirewallManager.remove_lan_firewall_rule()
            self._toast_callback(t("settings.lan_disabled"), "info")

        if self.page:
            self.page.update()

    @property
    def value(self) -> bool:
        return self._switch.value
