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
        self.wave_chart = wave_chart
        wave_header = ft.Row(
            [
                ft.Row(
                    [
                        ft.Container(
                            width=6,
                            height=6,
                            border_radius=3,
                            bgcolor="#38BDF8",
                        ),
                        ft.Text(
                            t(
                                "stats.realtime_wave",
                                default="Real-Time Traffic Wave Stream",
                            ),
                            size=11,
                            weight=ft.FontWeight.W_300,
                            color=ft.Colors.with_opacity(0.60, ft.Colors.WHITE),
                        ),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        ft.Container(width=6, height=6, border_radius=3, bgcolor="#a855f7"),
                        ft.Text(
                            t("stats.download", default="Download"),
                            size=10,
                            color=ft.Colors.with_opacity(0.50, ft.Colors.WHITE),
                            weight=ft.FontWeight.W_300,
                        ),
                        ft.Container(width=6),
                        ft.Container(width=6, height=6, border_radius=3, bgcolor="#38bdf8"),
                        ft.Text(
                            t("stats.upload", default="Upload"),
                            size=10,
                            color=ft.Colors.with_opacity(0.50, ft.Colors.WHITE),
                            weight=ft.FontWeight.W_300,
                        ),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        super().__init__(
            content=ft.Column([wave_header, self.wave_chart], spacing=10),
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
            border_radius=14,
            padding=16,
            expand=True,
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
