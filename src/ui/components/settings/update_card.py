"""App Update Card component for Settings Page.

Features:
- Displays the client version + a "Check for Updates" outlined button.
- While checking, the button shows a small progress ring AND the whole card
  gets a neon sweep-glow border (same visual language as the connection
  button's pinging animation): a GPU-rotated SweepGradient disc behind an
  opaque mask, exposing only a thin glowing rim.
- The sweep is armed on mount (rotate=0.0 anchor committed) so the first
  0 -> 2π transition interpolates instead of being dropped.
"""

from __future__ import annotations

import math
from typing import Callable, Optional

import flet as ft

from src.core.constants import APP_VERSION
from src.core.i18n import t
from src.ui.theme import AppColors, create_glass_container

# Neon sweep palette (matches the connection button's pinging animation)
SWEEP_COLORS = ["#A3A8FE", "#00F2FE", "#00000000", "#00000000"]
SWEEP_STOPS = [0.0, 0.10, 0.22, 1.0]


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

        ACCENT = "#A3A8FE"
        self._btn_icon = ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT, size=16, color=ACCENT)
        self._btn_text = ft.Text(
            t("settings.check_updates", default="Check for Updates"),
            size=12,
            color=ACCENT,
            weight=ft.FontWeight.W_600,
        )
        self._progress_ring = ft.ProgressRing(
            width=16,
            height=16,
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
            spacing=6,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        )

        self._update_btn = ft.OutlinedButton(
            content=self._btn_container,
            width=160,
            height=34,
            style=ft.ButtonStyle(
                color=ACCENT,
                side=ft.BorderSide(1, ACCENT),
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding(12, 0, 12, 0),
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

        # ------------------------------------------------------------------
        # Neon sweep-glow border (inspection-style animation while checking)
        # ------------------------------------------------------------------
        # A large rotating disc carrying the SweepGradient, positioned so it
        # never contributes to layout size, clipped to this card. An OPAQUE
        # mask covers the gradient centre so only a thin glowing rim shows
        # around the card's edge. GPU-rotated via animate_rotation; the disc
        # stays mounted (visible) so Flutter keeps its rotation anchor.
        self._sweep_gradient = ft.SweepGradient(
            center=ft.Alignment.CENTER,
            colors=SWEEP_COLORS,
            stops=SWEEP_STOPS,
            rotation=0.0,
        )

        self._sweep_disc = ft.Container(
            width=700,
            height=700,
            border_radius=350,
            gradient=None,  # hidden until checking
            left=(360 - 700) / 2,
            top=(70 - 700) / 2,
            rotate=ft.Rotate(angle=0.0),
            animate_rotation=ft.Animation(
                duration=1500,
                curve=ft.AnimationCurve.LINEAR,
            ),
        )

        # Opaque mask: exactly the card's inner area, covering the gradient's
        # centre so only the ~2px outer rim glows.
        self._sweep_mask = ft.Container(
            bgcolor=glass.bgcolor,  # match card surface
            border_radius=12,
            visible=False,
        )

        self._sweep_animating = False
        self._sweep_task: Optional[asyncio.Task] = None  # type: ignore[name-defined]

        super().__init__(
            content=ft.Stack(
                [
                    self._sweep_disc,
                    self._sweep_mask,
                    ft.Container(
                        content=glass.content,
                        bgcolor=glass.bgcolor,
                        border=glass.border,
                        border_radius=glass.border_radius,
                        blur=glass.blur,
                        padding=glass.padding,
                    ),
                ],
                alignment=ft.Alignment.CENTER,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            ),
            bgcolor=glass.bgcolor,
            border=glass.border,
            border_radius=glass.border_radius,
            blur=glass.blur,
            padding=glass.padding,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    def did_mount(self):
        """Arm the sweep disc baseline during mount (same as ConnectionButton).

        Committing ``rotate=0.0`` as part of the card's own mount lets Flutter
        establish the rotation anchor on Frame 0, so the first check-update's
        0 -> 2π nudge interpolates instead of being dropped.
        """
        self._sweep_disc.visible = True
        self._sweep_disc.rotate = ft.Rotate(angle=0.0)
        try:
            self._sweep_disc.update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_checking(self, checking: bool) -> None:
        """Toggle the loading indicator AND the neon sweep glow on the card."""
        self._update_btn.disabled = checking
        self._btn_icon.visible = not checking
        self._progress_ring.visible = checking
        self._btn_text.value = (
            t("settings.checking_updates", default="Checking...")
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
        if self._sweep_animating:
            return
        self._sweep_animating = True
        self._sweep_disc.gradient = self._sweep_gradient
        self._sweep_mask.visible = True
        try:
            self._sweep_disc.update()
        except Exception:
            pass
        try:
            self._sweep_mask.update()
        except Exception:
            pass
        self._sweep_task = self._schedule_animation(self._sweep_loop)

    def stop_glow_animation(self) -> None:
        """Stop the sweep and hide the mask + gradient instantly."""
        self._sweep_animating = False
        if self._sweep_task and hasattr(self._sweep_task, "cancel"):
            try:
                self._sweep_task.cancel()
            except Exception:
                pass
        self._sweep_task = None
        self._sweep_disc.rotate = ft.Rotate(angle=0.0)
        self._sweep_disc.gradient = None
        self._sweep_mask.visible = False
        try:
            self._sweep_disc.update()
        except Exception:
            pass
        try:
            self._sweep_mask.update()
        except Exception:
            pass

    async def _sweep_loop(self):
        """Drive the native GPU rotation of the sweep disc while checking."""
        import asyncio

        try:
            # Frame flush: let the rotate=0.0 anchor render before nudging.
            await asyncio.sleep(0.05)
            if not self._sweep_animating:
                return
            full_turns = 0
            while self._sweep_animating:
                full_turns += 1
                self._sweep_disc.rotate = ft.Rotate(angle=2 * math.pi * full_turns)
                try:
                    self._sweep_disc.update()
                except Exception:
                    pass
                await asyncio.sleep(1.4)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            self._sweep_disc.rotate = ft.Rotate(angle=0.0)

    def _schedule_animation(self, coro_factory):
        """Schedule an animation coroutine, safe from the UI loop and background threads."""
        try:
            import asyncio

            page = self.page
            running = asyncio.get_running_loop()
            page_loop = getattr(getattr(getattr(page, "session", None), "connection", None), "loop", None)
            if running is not None and page_loop is not None and running is page_loop:
                return asyncio.create_task(coro_factory())
            return page.run_task(coro_factory)
        except Exception:
            return None

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
