"""App Update Card component for Settings Page.

While "Check for Updates" is running, the card shows the same neon sweep-glow
border used by the server inspection animation (ConfigCard): a GPU-rotated
SweepGradient disc sized to the card's diagonal, clipped to the card, exposing
only a thin glowing rim around the edge. The button itself stays compact and
clean — just an outlined pill with an icon and label; while checking it swaps
the icon for a small progress ring.

The disc is sized via on_size_change (diagonal) exactly like ConfigCard, so
the sweep always traces every edge without clipping artifacts.
"""

from __future__ import annotations

import math
from typing import Callable, Optional

import flet as ft

from src.core.constants import APP_VERSION
from src.core.i18n import t
from src.ui.theme import AppColors, create_glass_container

# Neon sweep palette (matches the inspection animation)
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
        self._btn_icon = ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT, size=15, color=ACCENT)
        self._btn_text = ft.Text(
            t("settings.check_updates", default="Check for Updates"),
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
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        # ------------------------------------------------------------------
        # Neon sweep-glow border — EXACT same pattern as ConfigCard inspection
        # ------------------------------------------------------------------
        # A large rotating disc carrying the SweepGradient, positioned so it
        # never contributes to layout size, clipped to this card. The disc is
        # sized to the card's diagonal via on_size_change (so the rotating arc
        # traces every edge). Appearance is controlled solely by `gradient`
        # (None while idle); the disc stays mounted so Flutter keeps its
        # rotation anchor.
        self._disc_diameter = 600.0
        self._sweep_gradient = ft.SweepGradient(
            center=ft.Alignment.CENTER,
            colors=SWEEP_COLORS,
            stops=SWEEP_STOPS,
            rotation=0.0,
        )

        self._sweep_disc = ft.Container(
            width=self._disc_diameter,
            height=self._disc_diameter,
            border_radius=self._disc_diameter / 2,
            left=(360 - self._disc_diameter) / 2,
            top=(70 - self._disc_diameter) / 2,
            gradient=None,  # hidden until checking
            rotate=ft.Rotate(angle=0.0),
            animate_rotation=ft.Animation(
                duration=1500,
                curve=ft.AnimationCurve.LINEAR,
            ),
        )

        self._sweep_animating = False
        self._sweep_task: Optional[asyncio.Task] = None  # type: ignore[name-defined]

        super().__init__(
            content=ft.Stack(
                [self._sweep_disc, glass],
                alignment=ft.Alignment.CENTER,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            ),
            bgcolor=glass.bgcolor,
            border=glass.border,
            border_radius=glass.border_radius,
            blur=glass.blur,
            padding=glass.padding,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            on_size_change=self._on_size_changed,
        )

    def _on_size_changed(self, e):
        """Size the sweep disc to this card's diagonal (same as ConfigCard)."""
        w = getattr(e, "width", None)
        h = getattr(e, "height", None)
        if not w or not h:
            return
        w, h = float(w), float(h)
        diameter = math.hypot(w, h)
        self._disc_diameter = diameter
        self._sweep_disc.width = diameter
        self._sweep_disc.height = diameter
        self._sweep_disc.border_radius = diameter / 2
        self._sweep_disc.left = (w - diameter) / 2
        self._sweep_disc.top = (h - diameter) / 2
        try:
            self._sweep_disc.update()
        except Exception:
            pass

    def did_mount(self):
        """Arm the sweep disc baseline during mount (same as ConfigCard)."""
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
        try:
            self._sweep_disc.update()
        except Exception:
            pass
        self._sweep_task = self._schedule_animation(self._sweep_loop)

    def stop_glow_animation(self) -> None:
        """Stop the sweep and hide the gradient instantly."""
        self._sweep_animating = False
        if self._sweep_task and hasattr(self._sweep_task, "cancel"):
            try:
                self._sweep_task.cancel()
            except Exception:
                pass
        self._sweep_task = None
        self._sweep_disc.rotate = ft.Rotate(angle=0.0)
        self._sweep_disc.gradient = None
        try:
            self._sweep_disc.update()
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
