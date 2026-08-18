"""Xray-Core Update Card component for Settings Page.

While "Check Core Update" is running, the card shows the same neon sweep-glow
border used by the client update card (UpdateCard): a GPU-rotated
SweepGradient disc clipped to the button, exposing only a thin glowing rim
tracing the button's edge. No spinner — the neon rim IS the indicator.

The sweep animation lives in ONE shared component
(:class:`src.ui.components.common.neon_sweep_border.NeonSweepBorder`) used by
ConfigCard (server inspection) and UpdateCard (check client updates) too —
this card only wraps its button in it.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.services.xray_installer import XrayInstallerService
from src.ui.components.common.neon_sweep_border import NeonSweepBorder
from src.ui.theme import AppColors, create_glass_container

ACCENT = "#A3A8FE"


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

        self._btn_icon = ft.Icon(ft.Icons.MEMORY, size=15, color=ACCENT)
        self._btn_text = ft.Text(
            t("settings.check_core_update", default="Check Core Update"),
            size=12,
            color=ACCENT,
            weight=ft.FontWeight.W_600,
        )

        self._btn_container = ft.Row(
            [
                self._btn_icon,
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
            # Explicit width (fits inside the 180 wrapper) so the label swap
            # "Check Core Update" <-> "Updating..." NEVER resizes the button.
            width=170,
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

        # ------------------------------------------------------------------
        # Neon sweep-glow border — the SHARED reusable component
        # ------------------------------------------------------------------
        # A large rotating disc carrying the SweepGradient, positioned so it
        # never contributes to layout size, clipped to the button. Only a thin
        # neon rim traces the button's edge while checking. The OPAQUE inner
        # layer (the wrapper's mask) hides the disc center: the button itself
        # is see-through, so without it the whole spinning disc would bleed
        # through its face.
        self._neon = NeonSweepBorder(
            child=self._update_btn,
            width=180,
            height=32,
            border_radius=8,
        )

        # Legacy aliases (same objects as the component's internals) — the
        # pre-refactor card owned these names.
        self._sweep_gradient = self._neon._sweep_gradient
        self._sweep_disc = self._neon._disc
        self._disc_diameter = self._neon._disc_diameter
        self._inner_button_container = self._neon._inner
        self._btn_wrapper = self._neon

        glass = create_glass_container(
            content=ft.Row(
                [info_col, self._btn_wrapper],
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

        self._sweep_animating = False
        self._sweep_task = None

    def set_checking(self, checking: bool) -> None:
        """Toggle the neon sweep-glow border on the Check Core button.

        The icon stays ALWAYS visible (no visibility toggle) so the button
        never resizes — only the label and the glow change.
        """
        self._update_btn.disabled = checking
        self._btn_text.value = (
            t("settings.checking_core_updates", default="Updating...")
            if checking
            else t("settings.check_core_update", default="Check Core Update")
        )

        if checking:
            self.start_glow_animation()
        else:
            self.stop_glow_animation()

        try:
            if self._update_btn.page:
                self._update_btn.update()
        except Exception:
            pass

    def start_glow_animation(self) -> None:
        """Start the neon sweep-glow border while checking for core updates."""
        self._neon.start()
        self._sweep_animating = self._neon.is_animating
        self._sweep_task = self._neon._sweep_task

    def stop_glow_animation(self) -> None:
        """Stop the sweep and hide the gradient instantly."""
        self._neon.stop()
        self._sweep_animating = False
        self._sweep_task = None

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
            self._btn_text.value = t("settings.checking_core_updates", default="Updating...")
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def did_mount(self) -> None:
        """Flet lifecycle hook — forward to the shared sweep component."""
        self._neon.did_mount()

    def _handle_click(self, e):
        if self._on_check_core_click:
            self._on_check_core_click(e)
