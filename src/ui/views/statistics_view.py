"""Statistics View Component - Dedicated Network Statistics and Wave Chart Analytics Page."""

from __future__ import annotations

import math
from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors, create_glass_container


def parse_size_to_bytes(size_str: str) -> float:
    """Parse size string (e.g. '12.4 MB', '500 KB', '1.2 GB', '1024 B') into bytes float."""
    if not size_str:
        return 0.0
    try:
        parts = size_str.strip().split()
        if not parts:
            return 0.0
        val = float(parts[0])
        unit = parts[1].upper() if len(parts) > 1 else "B"
        if "GB" in unit:
            return val * 1024.0 * 1024.0 * 1024.0
        elif "MB" in unit:
            return val * 1024.0 * 1024.0
        elif "KB" in unit:
            return val * 1024.0
        else:
            return val
    except Exception:
        return 0.0


def format_bytes(bytes_val: float) -> str:
    """Format bytes into human-readable data transfer string."""
    if bytes_val < 1024:
        return f"{bytes_val:.0f} B"
    elif bytes_val < 1024 * 1024:
        return f"{(bytes_val / 1024.0):.1f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{(bytes_val / (1024.0 * 1024.0)):.1f} MB"
    else:
        return f"{(bytes_val / (1024.0 * 1024.0 * 1024.0)):.2f} GB"


class StatisticsView(ft.Container):
    """Fluent Integrated Statistics View with high-density wave chart, speed cards, and data transfer analytics."""

    def __init__(self, on_back_click: Callable | None = None):
        self._on_back_click = on_back_click
        self._is_connected = False
        self._is_online = True

        WHITE = ft.Colors.WHITE
        MUTED_WHITE = AppColors.ON_SURFACE_VARIANT
        PURPLE = AppColors.PRIMARY
        CYAN = ft.Colors.CYAN_400

        # --- 1. Header Area ---
        header_title_col = ft.Column(
            [
                ft.Text(
                    t("nav.statistics", default="Statistics & Analytics"),
                    size=11,
                    weight=ft.FontWeight.W_600,
                    color=MUTED_WHITE,
                ),
                ft.Text(
                    t("dashboard.network_traffic", default="Network Traffic Analytics"),
                    size=20,
                    weight=ft.FontWeight.W_700,
                    color=WHITE,
                ),
            ],
            spacing=2,
        )

        self._traffic_rate_badge = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.SUBTITLES_OUTLINED, size=14, color=CYAN),
                    ft.Text("0.0 MB/s", size=13, weight=ft.FontWeight.W_700, color=WHITE),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border_radius=16,
            bgcolor=ft.Colors.with_opacity(0.14, PURPLE),
            border=ft.Border.all(1.0, ft.Colors.with_opacity(0.3, PURPLE)),
        )

        top_header_row = ft.Row(
            [
                header_title_col,
                self._traffic_rate_badge,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # --- 2. Live Speed & Usage Metric Cards ---
        self._dl_speed_text = ft.Text("0.0 MB/s", size=18, weight=ft.FontWeight.W_700, color=WHITE)
        self._ul_speed_text = ft.Text("0.0 MB/s", size=18, weight=ft.FontWeight.W_700, color=WHITE)
        self._dl_total_text = ft.Text("0.0 MB", size=11, weight=ft.FontWeight.W_600, color=WHITE)
        self._ul_total_text = ft.Text("0.0 MB", size=11, weight=ft.FontWeight.W_600, color=WHITE)
        self._total_transfer_text = ft.Text("0.0 MB / 0.0 MB", size=18, weight=ft.FontWeight.W_700, color=CYAN)
        self._uptime_display_text = ft.Text("00:00:00", size=11, weight=ft.FontWeight.W_600, color=WHITE)
        self._peak_speed_text = ft.Text("0.0 MB/s", size=11, weight=ft.FontWeight.W_600, color=WHITE)

        self._peak_bps = 0.0

        card_dl_speed = self._build_stat_card(
            title=t("dashboard.download", default="Download Speed"),
            val_control=self._dl_speed_text,
            sub_title="Session: ",
            sub_val_control=self._dl_total_text,
            icon=ft.Icons.SOUTH_WEST_ROUNDED,
            icon_color=PURPLE,
        )

        card_ul_speed = self._build_stat_card(
            title=t("dashboard.upload", default="Upload Speed"),
            val_control=self._ul_speed_text,
            sub_title="Session: ",
            sub_val_control=self._ul_total_text,
            icon=ft.Icons.NORTH_EAST_ROUNDED,
            icon_color=CYAN,
        )

        card_total_stats = self._build_stat_card(
            title="Total Data Transfer",
            val_control=self._total_transfer_text,
            sub_title="Peak Speed: ",
            sub_val_control=self._peak_speed_text,
            icon=ft.Icons.SWAP_VERT_ROUNDED,
            icon_color="#a855f7",
        )

        cards_row = ft.Row(
            [
                card_dl_speed,
                card_ul_speed,
                card_total_stats,
            ],
            spacing=12,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # --- 3. High-Density Smooth Wave Visualizer ---
        NUM_WAVE_BARS = 32
        self._dl_history = [0.0] * 16
        self._ul_history = [0.0] * 16
        self._dl_bars = []
        self._ul_bars = []

        chart_row = ft.Row(
            spacing=3,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.END,
            height=160,
        )
        ANIM_SMOOTH = ft.Animation(650, ft.AnimationCurve.DECELERATE)

        for i in range(NUM_WAVE_BARS):
            fade_factor = 0.35 + 0.65 * (i / max(1, NUM_WAVE_BARS - 1))

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

        wave_header = ft.Row(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.GRAPHIC_EQ_ROUNDED, size=16, color=CYAN),
                        ft.Text(
                            "Real-Time Traffic Wave Stream",
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
                            "Download",
                            size=11,
                            color=MUTED_WHITE,
                            weight=ft.FontWeight.W_500,
                        ),
                        ft.Container(width=8),
                        ft.Container(width=8, height=8, border_radius=4, bgcolor="#38bdf8"),
                        ft.Text(
                            "Upload",
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

        visualizer_box = create_glass_container(
            content=ft.Column(
                [
                    wave_header,
                    ft.Container(
                        content=chart_row,
                        height=160,
                        padding=ft.Padding.symmetric(vertical=6),
                    ),
                ],
                spacing=8,
            ),
            expand=True,
            padding=16,
        )

        # --- 4. Full View Assembly ---
        content_column = ft.Column(
            [
                top_header_row,
                cards_row,
                visualizer_box,
            ],
            spacing=16,
            expand=True,
        )

        super().__init__(
            content=ft.WindowDragArea(content=content_column, expand=True),
            padding=20,
            expand=True,
            bgcolor=ft.Colors.TRANSPARENT,
        )

    def _build_stat_card(
        self,
        title: str,
        val_control: ft.Control,
        sub_title: str,
        sub_val_control: ft.Control,
        icon: str,
        icon_color: str,
    ) -> ft.Container:
        """Helper to create a bento stat card."""
        card_content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(icon, size=15, color=icon_color),
                            width=26,
                            height=26,
                            border_radius=13,
                            bgcolor=ft.Colors.with_opacity(0.16, icon_color),
                            alignment=ft.Alignment.CENTER,
                        ),
                        ft.Text(
                            title,
                            size=11,
                            weight=ft.FontWeight.W_600,
                            color=AppColors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                val_control,
                ft.Row(
                    [
                        ft.Text(sub_title, size=11, color=AppColors.ON_SURFACE_VARIANT),
                        sub_val_control,
                    ],
                    spacing=2,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=6,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        return create_glass_container(
            content=card_content,
            expand=True,
            padding=14,
            height=110,
        )

    @staticmethod
    def _compute_smooth_wave_heights(
        history: list[float],
        num_output: int = 32,
        min_h: float = 6.0,
        max_h: float = 160.0,
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

            idle_wave = 0.035 * (math.sin(i * 0.45) + 1.0)
            final_pct = max(val, idle_wave) if max(history) < 100.0 else val

            h = max(min_h, final_pct * max_h)
            heights.append(round(h, 2))

        return heights

    def set_connection_state(
        self,
        is_connected: bool,
        is_connecting: bool = False,
        is_disconnecting: bool = False,
    ):
        """Update connection state."""
        self._is_connected = is_connected
        if not is_connected and not is_connecting:
            self._dl_history = [0.0] * len(self._dl_history)
            self._ul_history = [0.0] * len(self._ul_history)
            self._peak_bps = 0.0
            for i in range(len(self._dl_bars)):
                self._dl_bars[i].height = 6.0
                self._ul_bars[i].height = 6.0

        try:
            if self.page:
                self.update()
        except Exception:
            pass

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
        """Update real-time traffic statistics and wave visualizer."""
        dl_text = speed_text if speed_text is not None else rate_str
        ul_speed_kb = upload_bps / 1024.0
        if ul_speed_kb < 1024.0:
            ul_text = f"{ul_speed_kb:.1f} KB/s"
        else:
            ul_text = f"{(ul_speed_kb / 1024.0):.1f} MB/s"

        u_str = upload_total if upload_total is not None else upload_str
        d_str = download_total if download_total is not None else download_str

        try:
            dl_b = float(download_bps)
            ul_b = float(upload_bps)
            cur_max = max(dl_b, ul_b)
            if cur_max > self._peak_bps:
                self._peak_bps = cur_max
                peak_kb = self._peak_bps / 1024.0
                self._peak_speed_text.value = (
                    f"{peak_kb:.1f} KB/s" if peak_kb < 1024.0 else f"{(peak_kb / 1024.0):.1f} MB/s"
                )
        except (ValueError, TypeError):
            pass

        if hasattr(self, "_traffic_rate_badge") and self._traffic_rate_badge.content:
            self._traffic_rate_badge.content.controls[1].value = dl_text
        self._dl_speed_text.value = dl_text
        self._ul_speed_text.value = ul_text
        dl_bytes = parse_size_to_bytes(d_str)
        ul_bytes = parse_size_to_bytes(u_str)
        self._total_transfer_text.value = format_bytes(dl_bytes + ul_bytes)

        self._dl_history.pop(0)
        self._dl_history.append(download_bps if self._is_connected else 0.0)
        self._ul_history.pop(0)
        self._ul_history.append(upload_bps if self._is_connected else 0.0)

        dl_heights = self._compute_smooth_wave_heights(self._dl_history, num_output=32, min_h=6.0, max_h=160.0)
        ul_heights = self._compute_smooth_wave_heights(self._ul_history, num_output=32, min_h=6.0, max_h=160.0)

        for i in range(len(self._dl_bars)):
            self._dl_bars[i].height = dl_heights[i]
            self._ul_bars[i].height = ul_heights[i]

        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def update_server_info(self, *args, **kwargs):
        """Update server info (optional)."""
        pass

    def update_internet_status(self, is_online: bool):
        """Update internet status."""
        self._is_online = is_online

    def update_uptime(self, uptime_str: str):
        """Update uptime display."""
        self._uptime_display_text.value = uptime_str
        try:
            if hasattr(self, "_uptime_display_text") and self._uptime_display_text.page:
                self._uptime_display_text.update()
        except Exception:
            pass
