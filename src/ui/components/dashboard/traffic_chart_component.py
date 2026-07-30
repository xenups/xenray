"""Traffic Chart Component - Live download/upload wave bars and rate badges."""

from __future__ import annotations

import math
import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors, create_glass_container


class TrafficChartComponent:
    """Bento container showing live traffic rate, smooth wave bars, and total upload/download stats."""

    def __init__(self):
        PURPLE = AppColors.PRIMARY
        CYAN = ft.Colors.CYAN_400
        WHITE = ft.Colors.WHITE
        MUTED_WHITE = AppColors.ON_SURFACE_VARIANT

        self._traffic_rate_badge = ft.Container(
            content=ft.Text("0.0 MB/s", size=12, weight=ft.FontWeight.W_700, color=WHITE),
            padding=ft.Padding.symmetric(horizontal=12, vertical=5),
            border_radius=18,
            bgcolor=ft.Colors.with_opacity(0.18, PURPLE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.35, PURPLE)),
        )
        self._upload_total_text = ft.Text("0.0 MB", size=15, weight=ft.FontWeight.W_800, color=WHITE)
        self._download_total_text = ft.Text("0.0 MB", size=15, weight=ft.FontWeight.W_800, color=WHITE)

        self._dl_history = [0.0] * 12
        self._ul_history = [0.0] * 12
        self._dl_bars = []
        self._ul_bars = []

        NUM_WAVE_BARS = 24
        chart_row = ft.Row(
            spacing=3,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.END,
            expand=True,
            height=60,
        )
        ANIM_SMOOTH = ft.Animation(600, ft.AnimationCurve.DECELERATE)

        for i in range(NUM_WAVE_BARS):
            fade_opacity = 0.35 + 0.65 * (i / max(1, NUM_WAVE_BARS - 1))

            dl_bar = ft.Container(
                height=4,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.BOTTOM_CENTER,
                    end=ft.Alignment.TOP_CENTER,
                    colors=[
                        ft.Colors.with_opacity(fade_opacity, PURPLE),
                        ft.Colors.with_opacity(0.0, PURPLE),
                    ],
                ),
                border_radius=ft.BorderRadius(top_left=5, top_right=5, bottom_left=2, bottom_right=2),
                animate=ANIM_SMOOTH,
                expand=True,
            )
            ul_bar = ft.Container(
                height=4,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.BOTTOM_CENTER,
                    end=ft.Alignment.TOP_CENTER,
                    colors=[
                        ft.Colors.with_opacity(fade_opacity * 0.85, CYAN),
                        ft.Colors.with_opacity(0.0, CYAN),
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

        chart_stack = ft.Container(content=chart_row, height=60)

        content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(
                                    t("dashboard.network_traffic", default="NETWORK TRAFFIC"),
                                    size=10,
                                    weight=ft.FontWeight.W_700,
                                    color=MUTED_WHITE,
                                ),
                                ft.Text(
                                    t("dashboard.live_statistics", default="Live Statistics"),
                                    size=18,
                                    weight=ft.FontWeight.W_800,
                                    color=WHITE,
                                ),
                            ],
                            spacing=1,
                        ),
                        self._traffic_rate_badge,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                chart_stack,
                ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(ft.Icons.ARROW_UPWARD, size=15, color=CYAN),
                                    width=28,
                                    height=28,
                                    shape=ft.BoxShape.CIRCLE,
                                    bgcolor=ft.Colors.with_opacity(0.18, CYAN),
                                    alignment=ft.Alignment.CENTER,
                                ),
                                ft.Column(
                                    [
                                        ft.Text(
                                            t("dashboard.upload", default="Upload"),
                                            size=10,
                                            color=MUTED_WHITE,
                                            weight=ft.FontWeight.W_600,
                                        ),
                                        self._upload_total_text,
                                    ],
                                    spacing=0,
                                ),
                            ],
                            spacing=8,
                        ),
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(ft.Icons.ARROW_DOWNWARD, size=15, color=PURPLE),
                                    width=28,
                                    height=28,
                                    shape=ft.BoxShape.CIRCLE,
                                    bgcolor=ft.Colors.with_opacity(0.18, PURPLE),
                                    alignment=ft.Alignment.CENTER,
                                ),
                                ft.Column(
                                    [
                                        ft.Text(
                                            t("dashboard.download", default="Download"),
                                            size=10,
                                            color=MUTED_WHITE,
                                            weight=ft.FontWeight.W_600,
                                        ),
                                        self._download_total_text,
                                    ],
                                    spacing=0,
                                ),
                            ],
                            spacing=8,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                ),
            ],
            spacing=6,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self.view = create_glass_container(
            content=content,
            expand=6,
            padding=14,
        )

    @staticmethod
    def _compute_smooth_wave_heights(
        history: list[float],
        num_output: int = 24,
        min_h: float = 4.0,
        max_h: float = 56.0,
    ) -> list[float]:
        """Compute smooth Catmull-Rom spline wave heights across num_output wave bars."""
        n = len(history)
        if n == 0:
            return [min_h] * num_output

        max_val = max(max(history), 1024.0 * 1024.0)
        norm = [min(1.0, max(0.0, float(v) / max_val)) for v in history]

        heights = []
        for i in range(num_output):
            pos = (i / max(1, num_output - 1)) * (n - 1)
            idx = int(pos)
            t_val = pos - idx

            p0 = norm[max(0, idx - 1)]
            p1 = norm[idx]
            p2 = norm[min(n - 1, idx + 1)]
            p3 = norm[min(n - 1, idx + 2)]

            val = 0.5 * (
                (2 * p1)
                + (-p0 + p2) * t_val
                + (2 * p0 - 5 * p1 + 4 * p2 - p3) * (t_val**2)
                + (-p0 + 3 * p1 - 3 * p2 + p3) * (t_val**3)
            )
            val = max(0.0, min(1.0, val))

            # Organic baseline ripple when traffic is low so wave bars stay fluid
            idle_wave = 0.035 * (math.sin(i * 0.45) + 1.0)
            final_pct = max(val, idle_wave) if max(history) < 100.0 else val

            h = max(min_h, final_pct * max_h)
            heights.append(round(h, 2))

        return heights

    def update_network_stats(
        self,
        rate_str: str = "0.0 MB/s",
        upload_str: str = "0.0 MB",
        download_str: str = "0.0 MB",
        download_bps: float = 0.0,
        upload_bps: float = 0.0,
        total_bps: float = 0.0,
        speed_text: str | None = None,
        upload_total: str | None = None,
        download_total: str | None = None,
    ):
        """Update live traffic statistics and smooth wave bar heights."""
        r_str = speed_text if speed_text is not None else rate_str
        u_str = upload_total if upload_total is not None else upload_str
        d_str = download_total if download_total is not None else download_str

        self._traffic_rate_badge.content.value = r_str
        self._upload_total_text.value = u_str
        self._download_total_text.value = d_str

        self._dl_history.pop(0)
        self._dl_history.append(download_bps)
        self._ul_history.pop(0)
        self._ul_history.append(upload_bps)

        dl_heights = self._compute_smooth_wave_heights(self._dl_history, num_output=24, min_h=4.0, max_h=56.0)
        ul_heights = self._compute_smooth_wave_heights(self._ul_history, num_output=24, min_h=4.0, max_h=56.0)

        for i in range(len(self._dl_bars)):
            self._dl_bars[i].height = dl_heights[i]
            self._ul_bars[i].height = ul_heights[i]

        try:
            if self.view.page:
                self.view.update()
        except Exception:
            pass
