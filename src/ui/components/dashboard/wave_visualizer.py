"""Wave Visualizer Component - high-density 32-bar real-time wave chart for network traffic analytics."""

from __future__ import annotations

from typing import List

import flet as ft


class WaveVisualizer(ft.Container):
    """32-bar dual-tone smooth real-time traffic wave visualizer."""

    def __init__(self, num_bars: int = 32) -> None:
        self._num_bars = num_bars
        # Persistent bar pool — allocated EXACTLY ONCE here. update_heights() only
        # mutates the existing instances' `height`; controls are never cleared or
        # recreated, so Flet's client can interpolate between ticks via the
        # animate/animate_size properties on the very same Container instances.
        self._bars: List[ft.Container] = []
        self._dl_bars: List[ft.Container] = []
        self._ul_bars: List[ft.Container] = []

        chart_row = ft.Row(
            spacing=3,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.END,
            height=160,
        )
        # 400ms ease-out interpolation between telemetry ticks (backend polling
        # stays untouched at 1s). ``animate_size`` interpolates bar height;
        # ``animate`` covers opacity/scale/offset on the same instances.
        ANIM_SMOOTH = ft.Animation(400, ft.AnimationCurve.EASE_OUT)

        for i in range(num_bars):
            fade_factor = 0.35 + 0.65 * (i / max(1, num_bars - 1))

            dl_bar = ft.Container(
                height=6,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.BOTTOM_CENTER,
                    end=ft.Alignment.TOP_CENTER,
                    colors=[
                        ft.Colors.with_opacity(fade_factor, "#a855f7"),
                        ft.Colors.with_opacity(0.0, "#a855f7"),
                    ],
                ),
                border_radius=ft.BorderRadius(top_left=5, top_right=5, bottom_left=2, bottom_right=2),
                animate=ANIM_SMOOTH,
                animate_size=ANIM_SMOOTH,
                expand=True,
            )
            ul_bar = ft.Container(
                height=6,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.BOTTOM_CENTER,
                    end=ft.Alignment.TOP_CENTER,
                    colors=[
                        ft.Colors.with_opacity(fade_factor * 0.85, "#38bdf8"),
                        ft.Colors.with_opacity(0.0, "#38bdf8"),
                    ],
                ),
                border_radius=ft.BorderRadius(top_left=5, top_right=5, bottom_left=2, bottom_right=2),
                animate=ANIM_SMOOTH,
                animate_size=ANIM_SMOOTH,
                expand=True,
            )

            slot = ft.Row(
                [dl_bar, ul_bar],
                spacing=1,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.END,
                expand=True,
            )
            self._bars.extend([dl_bar, ul_bar])
            self._dl_bars.append(dl_bar)
            self._ul_bars.append(ul_bar)
            chart_row.controls.append(slot)

        super().__init__(
            content=chart_row,
            height=160,
            padding=ft.Padding.symmetric(vertical=6),
        )

    def _is_attached(self) -> bool:
        """Return True only when this chart is mounted on a live page."""
        try:
            return getattr(self, "_page", None) is not None or self.page is not None
        except Exception:
            return getattr(self, "_page", None) is not None

    def update_heights(self, dl_heights: List[float], ul_heights: List[float]) -> None:
        """Mutate the existing bar instances' heights in place and refresh once.

        The bar Containers are allocated once in ``__init__`` and never replaced;
        only the ``height`` attribute changes here. A single ``self.update()`` on
        the parent lets Flet animate each bar from its previous height to the new
        target (600ms ease-out) without clearing or recreating any control.

        Bars are only touched when the chart is attached to a visible page; a
        hidden/detached chart skips all mutation so no CPU/GPU cycles are spent
        animating bars the user cannot see.
        """
        if not self._is_attached():
            return
        n = min(len(self._dl_bars), len(dl_heights), len(ul_heights))
        for i in range(n):
            self._dl_bars[i].height = dl_heights[i]
            self._ul_bars[i].height = ul_heights[i]
        try:
            self.update()
        except Exception:
            pass

    def reset_heights(self) -> None:
        """Reset wave bar heights to minimum idle baseline (6.0px)."""
        if not self._is_attached():
            return
        for i in range(len(self._dl_bars)):
            self._dl_bars[i].height = 6.0
            self._ul_bars[i].height = 6.0
        try:
            self.update()
        except Exception:
            pass
