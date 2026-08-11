"""Xray-Core Update Card component for Settings Page."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.services.xray_installer import XrayInstallerService
from src.ui.theme import AppColors, create_glass_container


class XrayCoreCard(ft.Container):
    """Card displaying Xray-Core binary version info and Check/Update Core action button."""

    def __init__(self, on_check_core_click: Callable):
        self._on_check_core_click = on_check_core_click
        WHITE = ft.Colors.WHITE

        current_ver = XrayInstallerService.get_local_version() or "ND"
        ver_display = f"v{current_ver}" if not current_ver.startswith("v") else current_ver

        self._version_text = ft.Text(
            t("settings.xray_core_version", default=ver_display, version=ver_display),
            size=12,
            color=AppColors.ON_SURFACE_VARIANT,
        )

        self._title_text = ft.Text(
            "Xray-Core",
            size=14,
            weight=ft.FontWeight.W_700,
            color=WHITE,
        )

        info_col = ft.Column(
            [
                self._title_text,
                self._version_text,
            ],
            spacing=2,
        )

        self._btn_icon = ft.Icon(ft.Icons.MEMORY, size=15, color=WHITE)
        self._btn_text = ft.Text(
            t("settings.check_core_update", default="بررسی آپدیت هسته"),
            size=12,
            color=AppColors.ON_PRIMARY,
            weight=ft.FontWeight.W_600,
        )
        self._progress_ring = ft.ProgressRing(
            width=14,
            height=14,
            stroke_width=2,
            color=WHITE,
            visible=False,
        )

        self._update_btn = ft.ElevatedButton(
            content=ft.Row(
                [
                    self._btn_icon,
                    self._progress_ring,
                    self._btn_text,
                ],
                spacing=6,
            ),
            style=ft.ButtonStyle(
                bgcolor=AppColors.PRIMARY,
                color=AppColors.ON_PRIMARY,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding.symmetric(horizontal=16, vertical=10),
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
        """Toggle loading indicator on Check Core button."""
        self._update_btn.disabled = checking
        self._btn_icon.visible = not checking
        self._progress_ring.visible = checking
        self._btn_text.value = (
            t("settings.checking_core_updates", default="در حال بررسی هسته...")
            if checking
            else t("settings.check_core_update", default="بررسی آپدیت هسته")
        )
        try:
            if self._update_btn.page:
                self._update_btn.update()
        except Exception:
            pass

    def refresh_version(self) -> None:
        """Refresh displayed Xray-Core version string."""
        current_ver = XrayInstallerService.get_local_version() or "ND"
        ver_display = f"v{current_ver}" if not current_ver.startswith("v") else current_ver
        self._version_text.value = t("settings.xray_core_version", default=ver_display, version=ver_display)
        try:
            if self._version_text.page:
                self._version_text.update()
        except Exception:
            pass

    def _handle_click(self, e):
        if self._on_check_core_click:
            self._on_check_core_click(e)
