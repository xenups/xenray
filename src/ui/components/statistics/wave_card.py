"""Wave Card component encapsulating WaveVisualizer, legend header, and glass panel."""

from __future__ import annotations

from typing import List

import flet as ft

from src.core.i18n import t
from src.ui.components.dashboard.wave_visualizer import WaveVisualizer
from src.ui.theme import AppColors, create_glass_container


class WaveCard(ft.Container):
    """Component wrapping WaveVisualizer with real-time legend header."""

    def __init__(self, wave_chart: WaveVisualizer):
        MUTED_WHITE = AppColors.ON_SURFACE_VARIANT
        CYAN = ft.Colors.CYAN_400

        self.wave_chart = wave_chart

        wave_header = ft.Row(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.GRAPHIC_EQ_ROUNDED, size=16, color=CYAN),
                        ft.Text(
                            t(
                                "stats.realtime_wave",
                                default="Real-Time Traffic Wave Stream",
                            ),
                            size=12,
                            weight=ft.FontWeight.W_600,
                            color=MUTED_WHITE,
                        ),
                    ],
                    spacing=6,
                ),
                ft.Row(
                    [
                        ft.Container(width=8, height=8, border_radius=4, bgcolor="#a855f7"),
                        ft.Text(
                            t("stats.download", default="Download"),
                            size=11,
                            color=MUTED_WHITE,
                            weight=ft.FontWeight.W_500,
                        ),
                        ft.Container(width=8),
                        ft.Container(width=8, height=8, border_radius=4, bgcolor="#38bdf8"),
                        ft.Text(
                            t("stats.upload", default="Upload"),
                            size=11,
                            color=MUTED_WHITE,
                            weight=ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=4,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        glass = create_glass_container(
            content=ft.Column([wave_header, self.wave_chart], spacing=8),
            expand=True,
            padding=16,
        )

        super().__init__(
            content=glass.content,
            bgcolor=glass.bgcolor,
            border=glass.border,
            border_radius=glass.border_radius,
            blur=glass.blur,
            padding=glass.padding,
            expand=glass.expand,
        )

    def update_telemetry(self, dl_heights: List[float], ul_heights: List[float]) -> None:
        """Reactively push new wave bar heights into the visualizer."""
        self.wave_chart.update_heights(dl_heights, ul_heights)
        try:
            self.update()
        except Exception:
            pass

    def reset_heights(self) -> None:
        """Reset the wave bars back to their idle baseline."""
        self.wave_chart.reset_heights()
        try:
            self.update()
        except Exception:
            pass
