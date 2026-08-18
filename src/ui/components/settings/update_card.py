"""App Update Card component for Settings Page.

A clean glass card showing the client version and a compact "Check for
Updates" action button. While checking, the button shows the SAME neon
sweep-glow border used by server inspection (ConfigCard): a GPU-rotated
SweepGradient disc clipped to the button, exposing only a thin glowing rim
tracing the button's edge. No spinner — the neon rim IS the indicator.

The sweep animation lives in ONE shared component
(:class:`src.ui.components.common.neon_sweep_border.NeonSweepBorder`) used by
ConfigCard (server inspection) and XrayCoreCard (check core update) too —
this card only wraps its button in it.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.constants import APP_VERSION
from src.core.i18n import t
from src.ui.components.common.neon_sweep_border import NeonSweepBorder
from src.ui.theme import AppColors, create_glass_container

ACCENT = "#A3A8FE"


class UpdateCard(ft.Container):
    """Card displaying client version info and Check for Updates action button."""

    def __init__(self, on_check_update_click: Callable):
        self._on_check_update_click = on_check_update_click

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
                    color=ft.Colors.WHITE,
                ),
                self._version_text,
            ],
            spacing=2,
        )

        self._btn_icon = ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT, size=15, color=ACCENT)
        self._btn_text = ft.Text(
            t("settings.check_updates", default="Check for Updates"),
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
            # "Check for Updates" <-> "Updating..." NEVER resizes the button.
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
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_checking(self, checking: bool) -> None:
        """Toggle the neon sweep-glow border on the button while checking.

        The icon stays ALWAYS visible (no visibility toggle) so the button
        never resizes — only the label and the glow change.
        """
        self._update_btn.disabled = checking
        self._btn_text.value = (
            t("settings.checking_updates", default="Updating...")
            if checking
            else t("settings.check_updates", default="Check for Updates")
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
        """Start the neon sweep-glow border while checking for updates."""
        self._neon.start()
        self._sweep_animating = self._neon.is_animating
        self._sweep_task = self._neon._sweep_task

    def stop_glow_animation(self) -> None:
        """Stop the sweep and hide the gradient instantly."""
        self._neon.stop()
        self._sweep_animating = False
        self._sweep_task = None

    def update_labels(self) -> None:
        """Update localized UI text labels dynamically."""
        ver_display = f"v{APP_VERSION}" if not str(APP_VERSION).startswith("v") else APP_VERSION
        self._version_text.value = t("settings.version", default=ver_display, version=ver_display)
        if not getattr(self._update_btn, "disabled", False):
            self._btn_text.value = t("settings.check_updates", default="Check for Updates")
        else:
            self._btn_text.value = t("settings.checking_updates", default="Updating...")
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def did_mount(self) -> None:
        """Flet lifecycle hook — forward to the shared sweep component."""
        self._neon.did_mount()

    def _handle_click(self, e):
        if self._on_check_update_click:
            self._on_check_update_click(e)
