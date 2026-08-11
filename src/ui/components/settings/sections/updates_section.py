"""Updates settings section - app client, Xray core, and routing rules update checkers."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.constants import APP_VERSION
from src.core.i18n import t
from src.ui.components.settings.base_rows import SettingsRow, SettingsSection

ACCENT = "#A3A8FE"


def _compact_outlined_button(label: str, on_click: Callable) -> ft.OutlinedButton:
    """Compact outlined action button used for the update checkers."""
    return ft.OutlinedButton(
        content=ft.Text(
            label,
            size=11,
            color=ACCENT,
            weight=ft.FontWeight.W_600,
        ),
        width=130,
        height=30,
        style=ft.ButtonStyle(
            color=ACCENT,
            side=ft.BorderSide(1, ACCENT),
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            bgcolor={
                ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
                ft.ControlState.HOVERED: ft.Colors.with_opacity(0.1, ACCENT),
            },
        ),
        on_click=on_click,
    )


class UpdatesSection(ft.Container):
    """System settings section composing the app/Xray/rules update checkers and About row."""

    def __init__(
        self,
        *,
        on_check_app_updates: Callable,
        on_check_xray_core: Callable,
        on_update_rules: Callable,
    ):
        self._app_btn = _compact_outlined_button(t("settings.check_updates"), on_check_app_updates)
        self._xray_btn = _compact_outlined_button(t("settings.check_core_update"), on_check_xray_core)
        self._rules_btn = _compact_outlined_button(t("settings.update_rules"), on_update_rules)

        version_display = f"v{APP_VERSION}" if not str(APP_VERSION).startswith("v") else APP_VERSION

        controls = [
            SettingsRow(
                ft.Icons.UPGRADE,
                t("settings.check_app_updates"),
                self._app_btn,
                t("settings.app_update_description"),
            ),
            SettingsRow(
                ft.Icons.SYSTEM_UPDATE_ALT,
                t("settings.check_updates"),
                self._xray_btn,
                t("settings.update_xray"),
            ),
            SettingsRow(
                ft.Icons.PUBLIC,
                t("settings.update_rules"),
                self._rules_btn,
                t("settings.update_rules_desc"),
            ),
            SettingsRow(
                ft.Icons.INFO_OUTLINE,
                t("settings.about"),
                ft.Text(
                    f"{version_display} by Xenups",
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ),
        ]

        super().__init__(
            content=SettingsSection(
                t("settings.system"),
                controls,
            )
        )

    @property
    def app_update_btn(self) -> ft.OutlinedButton:
        return self._app_btn

    @property
    def xray_update_btn(self) -> ft.OutlinedButton:
        return self._xray_btn

    @property
    def rules_update_btn(self) -> ft.OutlinedButton:
        return self._rules_btn
