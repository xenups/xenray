"""Wave Visualizer Component - high-density 32-bar real-time wave chart for network traffic analytics."""

from __future__ import annotations

from typing import List

import flet as ft


class WaveVisualizer(ft.Container):
    """32-bar dual-tone smooth real-time traffic wave visualizer."""

    def __init__(self, num_bars: int = 32) -> None:
        self._num_bars = num_bars
        self._dl_bars: List[ft.Container] = []
        self._ul_bars: List[ft.Container] = []

        chart_row = ft.Row(
            spacing=3,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.END,
            height=160,
        )
        ANIM_SMOOTH = ft.Animation(650, ft.AnimationCurve.DECELERATE)

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
                expand=True,
            )

            slot = ft.Row(
                [dl_bar, ul_bar],
                spacing=1,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.END,
                expand=True,
            )
            self._dl_bars.append(dl_bar)
            self._ul_bars.append(ul_bar)
            chart_row.controls.append(slot)

        super().__init__(
            content=chart_row,
            height=160,
            padding=ft.Padding.symmetric(vertical=6),
        )

    def update_heights(self, dl_heights: List[float], ul_heights: List[float]) -> None:
        """Update height properties across all 32 wave bars."""
        for i in range(min(len(self._dl_bars), len(dl_heights))):
            self._dl_bars[i].height = dl_heights[i]
            self._ul_bars[i].height = ul_heights[i]

    def reset_heights(self) -> None:
        """Reset wave bar heights to minimum idle baseline (6.0px)."""
        for i in range(len(self._dl_bars)):
            self._dl_bars[i].height = 6.0
            self._ul_bars[i].height = 6.0
