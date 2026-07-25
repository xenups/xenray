"""Traffic Chart Component - Live download/upload bars and rate badges."""

from __future__ import annotations

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors, create_glass_container


class TrafficChartComponent:
    """Bento container showing live traffic rate, history bars, and total upload/download stats."""

    def __init__(self):
        PURPLE = AppColors.PRIMARY
        PURPLE_DARK = AppColors.PRIMARY_CONTAINER
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

        chart_row = ft.Row(
            spacing=4,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.END,
            expand=True,
            height=60,
        )
        ANIM_SMOOTH = ft.Animation(500, ft.AnimationCurve.EASE_OUT_QUAD)
        for i in range(12):
            dl_bar = ft.Container(
                height=4,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.BOTTOM_CENTER,
                    end=ft.Alignment.TOP_CENTER,
                    colors=[PURPLE, ft.Colors.with_opacity(0.0, PURPLE)],
                ),
                border_radius=ft.BorderRadius(top_left=5, top_right=5, bottom_left=0, bottom_right=0),
                animate=ANIM_SMOOTH,
                expand=True,
            )
            ul_bar = ft.Container(
                height=4,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.BOTTOM_CENTER,
                    end=ft.Alignment.TOP_CENTER,
                    colors=[PURPLE_DARK, ft.Colors.with_opacity(0.0, PURPLE_DARK)],
                ),
                border_radius=ft.BorderRadius(top_left=5, top_right=5, bottom_left=0, bottom_right=0),
                animate=ANIM_SMOOTH,
                expand=True,
            )

            slot = ft.Row(
                [dl_bar, ul_bar],
                spacing=2,
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
                                    content=ft.Icon(ft.Icons.ARROW_UPWARD, size=15, color=PURPLE),
                                    width=28,
                                    height=28,
                                    shape=ft.BoxShape.CIRCLE,
                                    bgcolor=ft.Colors.with_opacity(0.18, PURPLE),
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
        """Update live traffic statistics and chart pillar heights."""
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

        max_val = max(max(self._dl_history), max(self._ul_history), 1024.0 * 1024.0)
        for i in range(12):
            dl_pct = min(1.0, self._dl_history[i] / max_val)
            ul_pct = min(1.0, self._ul_history[i] / max_val)

            dl_h = max(4.0, dl_pct * 56.0)
            ul_h = max(4.0, ul_pct * 56.0)

            self._dl_bars[i].height = dl_h
            self._ul_bars[i].height = ul_h

        try:
            if self.view.page:
                self.view.update()
        except Exception:
            pass
