"""Reusable neon sweep-glow border component.

Extracted from ConfigCard's inspection animation (server list) so every
caller — ConfigCard (server inspection), UpdateCard (check for updates),
XrayCoreCard (check core update) — shares ONE implementation instead of
forking ~60 lines of disc + rotation-loop code per card.

Pattern (identical to the original ConfigCard implementation):

- Outer :class:`NeonSweepBorder` itself is a ``ft.Container`` acting as the
  1.5px border frame: ``padding=1.5`` + ``clip_behavior=HARD_EDGE`` so the
  sweep only ever shows through the 1.5px gap around the opaque inner layer.
- ``content`` is a ``Stack`` of two layers:
  1. the rotating ``SweepGradient`` disc — a large (400px) circular layer
     POSITIONED with negative ``left``/``top`` offsets so it never sizes the
     Stack; appearance is controlled solely by ``gradient`` (None while idle),
     and it stays permanently mounted for rotation-anchor stability;
  2. the opaque inner ``ft.Container`` wrapping ``child`` with the caller's
     ``bgcolor`` — this is the mask that hides the disc center so only the
     thin neon rim is visible (a see-through inner control would let the
     whole spinning disc bleed through its face).

Public API: ``start()`` / ``stop()`` (with ConfigCard's mount-race deferred
start via ``did_mount()``) and the ``is_animating`` property. The 0.05s frame
flush, 1.4s cadence and ``CancelledError`` handling are copied verbatim from
ConfigCard's proven loop. SRP: this is pure UI — callers keep their own
semantics (ConfigCard's ``start_inspection_animation``, UpdateCard's
``set_checking``).
"""

from __future__ import annotations

import asyncio
import math
from typing import Optional

import flet as ft

from src.core.logger import logger

# Neon sweep palette (identical across ConfigCard / UpdateCard / XrayCoreCard).
SWEEP_COLORS = ["#A3A8FE", "#00F2FE", "#00000000", "#00000000"]
SWEEP_STOPS = [0.0, 0.10, 0.22, 1.0]

# Disc diameter: large enough to cover every wrapped target (ConfigCard's
# 360x62 card included). It is POSITIONED with negative offsets so it never
# contributes to Stack layout; callers may refine it via resize_disc().
_DISC_DIAMETER = 400.0


class NeonSweepBorder(ft.Container):
    """A 1.5px neon sweep-glow border frame around ``child``.

    Wraps any control with ConfigCard's exact inspection animation: a GPU-
    rotated SweepGradient disc clipped to the border frame, masked by an
    opaque inner container so only a thin glowing rim traces the edge. No
    spinner — the neon rim IS the indicator.
    """

    def __init__(
        self,
        child: ft.Control,
        width: Optional[float] = None,
        height: float = 32,
        border_radius: float = 8,
        opaque_bgcolor: str = "#161922",
    ):
        self._child = child

        # The SweepGradient disc layer. Stays permanently MOUNTED (never
        # toggled via visible); appearance is controlled solely by `gradient`
        # (None while idle). Constructed with the rotate=0.0 rotation ANCHOR
        # and the GPU animate_rotation already attached so Flutter can begin
        # interpolating the first target change immediately.
        self._sweep_gradient = ft.SweepGradient(
            center=ft.Alignment.CENTER,
            colors=SWEEP_COLORS,
            stops=SWEEP_STOPS,
            rotation=0.0,
        )
        self._disc_diameter = _DISC_DIAMETER
        self._disc = ft.Container(
            width=self._disc_diameter,
            height=self._disc_diameter,
            border_radius=self._disc_diameter / 2,
            left=(width - self._disc_diameter) / 2 if width else -self._disc_diameter / 2,
            top=(height - self._disc_diameter) / 2,
            gradient=None,
            rotate=ft.Rotate(angle=0.0),
            animate_rotation=ft.Animation(
                duration=1500,
                curve=ft.AnimationCurve.LINEAR,
            ),
        )

        # OPAQUE inner layer — the sizing child of the Stack. This is the
        # mask: the sweep gradient only shows through the 1.5px padding gap
        # around this layer (the thin neon rim). The wrapped control itself is
        # often see-through (e.g. an OutlinedButton with a transparent
        # bgcolor) and would otherwise let the whole spinning disc show
        # through its face.
        self._inner = ft.Container(
            content=child,
            height=height,
            bgcolor=opaque_bgcolor,
            border_radius=ft.BorderRadius.all(border_radius),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        super().__init__(
            content=ft.Stack(
                [self._disc, self._inner],
                alignment=ft.Alignment.CENTER,
                clip_behavior=ft.ClipBehavior.NONE,
            ),
            padding=ft.Padding.all(1.5),
            border_radius=border_radius,
            width=width,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        self._animating = False
        self._sweep_task: Optional[asyncio.Task] = None  # type: ignore[name-defined]
        self._pending_start = False

        # Adapt the disc diagonal at runtime when the wrapper is laid out.
        self.on_size_change = self._on_size_changed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_animating(self) -> bool:
        """True while the sweep loop is armed (gradient visible)."""
        return self._animating

    def start(self) -> None:
        """Arm the neon sweep-glow loop (gradient on + GPU rotation nudges)."""
        if self._animating:
            return
        self._animating = True
        self._disc.gradient = self._sweep_gradient
        if self._safe_page() is not None:
            self._schedule_animation()
        else:
            self._pending_start = True
        try:
            self._disc.update()
        except Exception:
            pass

    def stop(self) -> None:
        """Cancel the loop, hide the gradient and reset the rotation anchor."""
        self._animating = False
        self._pending_start = False
        if self._sweep_task and not self._sweep_task.done():
            self._sweep_task.cancel()
        self._sweep_task = None
        self._disc.rotate = ft.Rotate(angle=0.0)
        self._disc.gradient = None
        try:
            self._disc.update()
        except Exception:
            pass

    def resize_disc(self, w: float, h: float) -> None:
        """Size the disc to the wrapper's diagonal (no corner clipping).

        A rotating square disc clips its corners out of the thin border ring;
        sizing the disc to the diagonal (>= any rotated point's radius) keeps
        the neon arc tracing every edge without clipping artifacts.
        """
        w, h = float(w), float(h)
        if not w or not h:
            return
        diameter = math.hypot(w, h)
        self._disc_diameter = diameter
        self._disc.width = diameter
        self._disc.height = diameter
        self._disc.border_radius = diameter / 2
        self._disc.left = (w - diameter) / 2
        self._disc.top = (h - diameter) / 2
        try:
            self._disc.update()
        except Exception:
            pass

    def did_mount(self) -> None:
        """Flet lifecycle hook — start a pending sweep once attached.

        Mirrors ConfigCard's mount-race handling (two cases):
        1. start() ran while unmounted and is STILL armed -> schedule the
           sweep loop directly (re-entering start() would early-return).
        2. The sweep was stopped before mount -> re-enter the full start()
           path, now attached, so the animation is never silently lost.
        """
        if self._pending_start:
            self._pending_start = False
            if self._animating:
                self._schedule_animation()
            else:
                self.start()

    def will_unmount(self) -> None:
        """Cancel the sweep task on unmount."""
        self.stop()

    # ------------------------------------------------------------------
    # Internals (ConfigCard's proven implementation)
    # ------------------------------------------------------------------

    def _on_size_changed(self, e) -> None:
        w = getattr(e, "width", None)
        h = getattr(e, "height", None)
        if w and h:
            self.resize_disc(w, h)

    def _schedule_animation(self) -> None:
        """Schedule the sweep coroutine on an available event loop."""
        page = self._safe_page()
        if page is not None:
            if self._sweep_task is None or self._sweep_task.done():
                self._pending_start = False
                self._sweep_task = page.run_task(self._animate_sweep)
            return

        try:
            loop = asyncio.get_running_loop()
            if self._sweep_task is None or self._sweep_task.done():
                self._pending_start = False
                self._sweep_task = loop.create_task(self._animate_sweep())
        except RuntimeError:
            # No running event loop (built on a background thread, not yet
            # mounted). did_mount() schedules the loop once attached.
            pass

    async def _animate_sweep(self) -> None:
        """Drive the native GPU rotation of the sweep disc.

        Frame flush (0.05s) lets the 0.0 rotation anchor render before the
        first target, then the loop nudges the target forward by a full turn
        (2π) each cycle — one tiny ``rotate`` patch per 1.4s, interpolated at
        60 FPS on the GPU.
        """
        try:
            await asyncio.sleep(0.05)
            if not self._animating:
                return
            full_turns = 0
            while self._animating:
                full_turns += 1
                self._disc.rotate = ft.Rotate(angle=2 * math.pi * full_turns)
                try:
                    self._disc.update()
                except Exception:
                    pass
                await asyncio.sleep(1.4)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[NeonSweepBorder] Animation exception: {e}")
        finally:
            self._disc.rotate = ft.Rotate(angle=0.0)

    def _safe_page(self) -> Optional[ft.Page]:
        """RuntimeError-safe page property getter."""
        try:
            return self.page
        except (RuntimeError, AttributeError):
            return None
