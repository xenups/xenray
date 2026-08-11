"""Self-contained LAN proxy sharing toggle component for settings."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.event_bus import TOPIC_LAN_SHARING_CHANGED, event_bus
from src.core.i18n import t
from src.ui.controllers.lan_sharing_controller import LanSharingController


class LanShareToggleRow(ft.Container):
    """Self-contained LAN proxy sharing toggle component."""

    def __init__(
        self,
        app_context,
        toast_callback: Callable[[str, str], None],
    ):
        self._app_context = app_context
        self._toast_callback = toast_callback
        self._controller = LanSharingController(app_context=app_context)

        is_enabled = app_context.settings.get_allow_lan()
        self._switch = ft.Switch(
            value=is_enabled,
            active_color=ft.Colors.PRIMARY,
            on_change=self._handle_toggle,
        )

        event_bus.subscribe(TOPIC_LAN_SHARING_CHANGED, self._on_lan_sharing_changed)

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
        """Route the toggle through the unified LAN sharing controller."""
        enabled = self._switch.value
        self._controller.set_lan_sharing_enabled(enabled)

        if enabled:
            self._toast_callback(t("settings.lan_enabled"), "success")
        else:
            self._toast_callback(t("settings.lan_disabled"), "info")

    def _on_lan_sharing_changed(self, data) -> None:
        """Sync this switch whenever LAN sharing state changes anywhere."""
        if not isinstance(data, dict):
            return
        enabled = bool(data.get("enabled", self._switch.value))
        if self._switch.value != enabled:
            self._switch.value = enabled
        try:
            if self._switch.page:
                self._switch.update()
        except Exception:
            pass

    def dispose(self) -> None:
        """Release the EventBus subscription held by this row."""
        event_bus.unsubscribe(TOPIC_LAN_SHARING_CHANGED, self._on_lan_sharing_changed)

    @property
    def value(self) -> bool:
        return self._switch.value
