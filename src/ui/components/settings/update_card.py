"""App Update Card component for Settings Page."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.constants import APP_VERSION
from src.core.i18n import t
from src.ui.theme import AppColors, create_glass_container


class UpdateCard(ft.Container):
    """Card displaying client version info and Check for Updates action button."""

    def __init__(self, on_check_update_click: Callable):
        self._on_check_update_click = on_check_update_click
        WHITE = ft.Colors.WHITE

        ver_display = f"v{APP_VERSION}" if not str(APP_VERSION).startswith("v") else APP_VERSION

        self._version_text = ft.Text(
            t("settings.version", default=ver_display, version=ver_display),
            size=12,
            color=AppColors.ON_SURFACE_VARIANT,
        )

        info_col = ft.Column(
            [
                ft.Text(
                    "XenRay Client",
                    size=14,
                    weight=ft.FontWeight.W_700,
                    color=WHITE,
                ),
                self._version_text,
            ],
            spacing=2,
        )

        self._btn_icon = ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT, size=15, color=WHITE)
        self._btn_text = ft.Text(
            t("settings.check_updates", default="Check for Updates"),
            size=12,
            color=AppColors.ON_PRIMARY,
            weight=ft.FontWeight.W_600,
        )
        self._progress_ring = ft.ProgressRing(
            width=18,
            height=18,
            stroke_width=2,
            color=WHITE,
            visible=False,
        )

        self._btn_container = ft.Container(
            content=ft.Row(
                [
                    self._btn_icon,
                    self._progress_ring,
                    self._btn_text,
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            width=160,
            height=24,
        )

        self._update_btn = ft.ElevatedButton(
            content=self._btn_container,
            width=180,
            height=40,
            style=ft.ButtonStyle(
                bgcolor=AppColors.PRIMARY,
                color=AppColors.ON_PRIMARY,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            ),
            on_click=self._handle_click,
        )

        glass = create_glass_container(
            content=ft.Row(
                [info_col, self._update_btn],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

        super().__init__(
            content=glass.content,
            bgcolor=glass.bgcolor,
            border=glass.border,
            border_radius=glass.border_radius,
            blur=glass.blur,
            padding=glass.padding,
        )

    def set_checking(self, checking: bool) -> None:
        """Toggle loading indicator on Check for Updates button."""
        self._update_btn.disabled = checking
        self._btn_icon.visible = not checking
        self._progress_ring.visible = checking
        self._btn_text.value = (
            t("settings.checking_updates", default="Checking...")
            if checking
            else t("settings.check_updates", default="Check for Updates")
        )
        try:
            if self._update_btn.page:
                self._update_btn.update()
        except Exception:
            pass

    def update_labels(self) -> None:
        """Update localized UI text labels dynamically."""
        ver_display = f"v{APP_VERSION}" if not str(APP_VERSION).startswith("v") else APP_VERSION
        self._version_text.value = t("settings.version", default=ver_display, version=ver_display)
        if not getattr(self._update_btn, "disabled", False):
            self._btn_text.value = t("settings.check_updates", default="Check for Updates")
        else:
            self._btn_text.value = t("settings.checking_updates", default="Checking...")
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def _handle_click(self, e):
        if self._on_check_update_click:
            self._on_check_update_click(e)
