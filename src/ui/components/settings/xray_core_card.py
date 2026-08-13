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

        ACCENT = "#A3A8FE"
        self._btn_icon = ft.Icon(ft.Icons.MEMORY, size=15, color=ACCENT)
        self._btn_text = ft.Text(
            t("settings.check_core_update", default="Check Core Update"),
            size=12,
            color=ACCENT,
            weight=ft.FontWeight.W_600,
        )
        self._progress_ring = ft.ProgressRing(
            width=14,
            height=14,
            stroke_width=2,
            color=ACCENT,
            visible=False,
        )

        self._btn_container = ft.Row(
            [
                self._btn_icon,
                self._progress_ring,
                self._btn_text,
            ],
            spacing=5,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        )

        self._update_btn = ft.OutlinedButton(
            content=self._btn_container,
            height=32,
            style=ft.ButtonStyle(
                color=ACCENT,
                side=ft.BorderSide(1, ACCENT),
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding.symmetric(horizontal=12),
                bgcolor={
                    ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
                    ft.ControlState.HOVERED: ft.Colors.with_opacity(0.1, ACCENT),
                },
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
            t("settings.checking_core_updates", default="Checking core updates...")
            if checking
            else t("settings.check_core_update", default="Check Core Update")
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
        self._version_text.value = t(
            "settings.xray_core_version", default=f"Xray-Core {ver_display}", version=ver_display
        )
        try:
            if self._version_text.page:
                self._version_text.update()
        except Exception:
            pass

    def update_labels(self) -> None:
        """Update localized UI text labels dynamically."""
        self.refresh_version()
        if not getattr(self._update_btn, "disabled", False):
            self._btn_text.value = t("settings.check_core_update", default="Check Core Update")
        else:
            self._btn_text.value = t("settings.checking_core_updates", default="Checking core updates...")
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def _handle_click(self, e):
        if self._on_check_core_click:
            self._on_check_core_click(e)
