"""Dashboard View Component matching Fluent Integrated UI design specs (image_54.png)."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.country_translator import translate_country
from src.core.i18n import t
from src.ui.components.connection_button import ConnectionButton
from src.ui.theme import AppColors


class DashboardView(ft.Container):
    """Fluent Integrated Dashboard View with glassmorphism connection button, status text underneath, and real network stats chart."""

    def __init__(
        self,
        on_toggle_click: Callable,
        on_change_server_click: Callable,
        on_open_statistics_click: Callable | None = None,
        connection_button: ConnectionButton | None = None,
    ):
        self._on_toggle_click = on_toggle_click
        self._on_change_server_click = on_change_server_click
        self._on_open_statistics_click = on_open_statistics_click

        WHITE = ft.Colors.WHITE
        MUTED_WHITE = AppColors.ON_SURFACE_VARIANT

        self._is_connected = False
        self._is_online = True

        # --- 1. Top-Left Server Info ---
        self._flag_img = ft.Image(
            src="https://flagcdn.com/w40/fi.png",
            width=28,
            height=28,
            fit="cover",
            border_radius=14,
            visible=True,
        )

        self._server_name_text = ft.Text(
            "BunkerBuster (FI)",
            size=15,
            weight=ft.FontWeight.W_700,
            color=WHITE,
        )

        self._server_info_row = ft.Row(
            [
                ft.Container(
                    content=self._flag_img,
                    width=28,
                    height=28,
                    border_radius=14,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
                self._server_name_text,
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # --- 2. Top-Right Precise Data Stats ---
        self._dl_value_text = ft.Text(
            "D: 0.0 MB/s", size=12, weight=ft.FontWeight.W_600, color=WHITE
        )
        self._ul_value_text = ft.Text(
            "U: 0.0 MB/s", size=12, weight=ft.FontWeight.W_600, color=WHITE
        )

        self._data_stats_column = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.SOUTH_WEST_ROUNDED, size=13, color=MUTED_WHITE
                        ),
                        self._dl_value_text,
                    ],
                    spacing=4,
                    alignment=ft.MainAxisAlignment.END,
                ),
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.NORTH_EAST_ROUNDED, size=13, color=MUTED_WHITE
                        ),
                        self._ul_value_text,
                    ],
                    spacing=4,
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            spacing=2,
            horizontal_alignment=ft.CrossAxisAlignment.END,
        )

        top_canvas_row = ft.Row(
            [
                self._server_info_row,
                self._data_stats_column,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        # --- 3. Central Glassmorphism Button & Status Area ---
        self._toggle_button = (
            connection_button
            if connection_button is not None
            else ConnectionButton(on_click=self._on_toggle_click)
        )

        self._center_status_text = ft.Text(
            t("dashboard.disconnected", default="Disconnected"),
            size=15,
            weight=ft.FontWeight.W_700,
            color=WHITE,
        )
        self._uptime_text = ft.Text(
            "00:00:00",
            size=12,
            weight=ft.FontWeight.W_500,
            color=MUTED_WHITE,
        )

        centerpiece_layout = ft.Column(
            [
                self._toggle_button,
                ft.Column(
                    [
                        self._center_status_text,
                        self._uptime_text,
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=16,
        )

        centerpiece_container = ft.Container(
            content=centerpiece_layout,
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

        # History tracking for stats compatibility
        self._dl_history = [0.0] * 12
        self._ul_history = [0.0] * 12
        self._dl_bars = []
        self._ul_bars = []

        # --- 4. Bottom Quick Link to Dedicated Statistics View ---
        self._bottom_stats_row = ft.Row(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.GRAPHIC_EQ_ROUNDED, size=15, color="#38bdf8"),
                        ft.Text(
                            t(
                                "dashboard.realtime_wave",
                                default="Live Wave Stream & Detailed Traffic Stats",
                            ),
                            size=11,
                            color=MUTED_WHITE,
                        ),
                    ],
                    spacing=6,
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.BAR_CHART_ROUNDED, size=14, color="#c084fc"
                            ),
                            ft.Text(
                                t(
                                    "dashboard.view_statistics",
                                    default="Statistics Page 📊",
                                ),
                                size=12,
                                weight=ft.FontWeight.W_700,
                                color=WHITE,
                            ),
                        ],
                        spacing=6,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                    border_radius=12,
                    bgcolor=ft.Colors.with_opacity(0.15, "#a855f7"),
                    border=ft.Border.all(1.0, ft.Colors.with_opacity(0.4, "#a855f7")),
                    on_click=lambda e: (
                        self._on_open_statistics_click(e)
                        if self._on_open_statistics_click
                        else None
                    ),
                    ink=True,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        visualizer_container = ft.Container(
            content=self._bottom_stats_row,
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            alignment=ft.Alignment.CENTER,
        )

        # --- 5. Full Canvas Layout Assembly ---
        canvas_layout = ft.Column(
            [
                top_canvas_row,
                centerpiece_container,
                visualizer_container,
            ],
            spacing=0,
            expand=True,
        )

        super().__init__(
            content=ft.WindowDragArea(content=canvas_layout, expand=True),
            padding=20,
            expand=True,
            bgcolor=ft.Colors.TRANSPARENT,
        )

    @staticmethod
    def _compute_smooth_wave_heights(
        history: list[float],
        num_output: int = 24,
        min_h: float = 4.0,
        max_h: float = 95.0,
    ) -> list[float]:
        """Compute smooth Catmull-Rom spline wave heights across num_output wave bars."""
        import math

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

            idle_wave = 0.03 * (math.sin(i * 0.45) + 1.0)
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
        """Update connection button state and centerpiece text underneath."""
        self._is_connected = is_connected

        if is_disconnecting:
            self._center_status_text.value = t(
                "status.disconnecting", default="Disconnecting..."
            )
            self._toggle_button.set_disconnecting()
        elif is_connecting:
            self._center_status_text.value = t(
                "status.connecting", default="Connecting..."
            )
            self._toggle_button.set_connecting()
        elif is_connected:
            self._center_status_text.value = t(
                "dashboard.connected", default="Connected"
            )
            self._toggle_button.set_connected()
        else:
            self._center_status_text.value = t(
                "dashboard.disconnected", default="Disconnected"
            )
            self._uptime_text.value = "00:00:00"
            self._toggle_button.set_disconnected()
            self._dl_history = [0.0] * len(self._dl_history)
            self._ul_history = [0.0] * len(self._ul_history)
            for i in range(len(self._dl_bars)):
                self._dl_bars[i].height = 4.0
                self._ul_bars[i].height = 4.0

        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def set_step(self, step_text: str):
        """Update center status text underneath button."""
        if (
            hasattr(self, "_center_status_text")
            and self._center_status_text
            and step_text
        ):
            self._center_status_text.value = step_text
            try:
                if self._center_status_text.page:
                    self._center_status_text.update()
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
        """Update top-right precise data values and render real network traffic stats on chart."""
        dl_text = speed_text if speed_text is not None else rate_str
        ul_speed_kb = upload_bps / 1024.0
        if ul_speed_kb < 1024.0:
            ul_text = f"{ul_speed_kb:.1f} KB/s"
        else:
            ul_text = f"{(ul_speed_kb / 1024.0):.1f} MB/s"

        self._dl_value_text.value = f"D: {dl_text}"
        self._ul_value_text.value = f"U: {ul_text}"

        self._dl_history.pop(0)
        self._dl_history.append(download_bps if self._is_connected else 0.0)
        self._ul_history.pop(0)
        self._ul_history.append(upload_bps if self._is_connected else 0.0)

        if hasattr(self, "_dl_bars") and self._dl_bars:
            dl_heights = self._compute_smooth_wave_heights(
                self._dl_history, num_output=len(self._dl_bars), min_h=4.0, max_h=95.0
            )
            ul_heights = self._compute_smooth_wave_heights(
                self._ul_history, num_output=len(self._dl_bars), min_h=4.0, max_h=95.0
            )

            for i in range(len(self._dl_bars)):
                self._dl_bars[i].height = dl_heights[i]
                self._ul_bars[i].height = ul_heights[i]

        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def update_glow_intensity(self, total_bps: float = 0.0):
        """Delegate glow intensity updates to connection button."""
        if self._toggle_button:
            self._toggle_button.update_network_activity(total_bps)

    def update_server_info(
        self,
        name: str = "",
        latency: str = "",
        protocol: str = "",
        encryption: str = "",
        server_ip: str = "",
        country_code: str = "",
        country_name: str = "",
        local_ip: str | None = None,
        **kwargs,
    ):
        """Update top-left server title and circular flag image."""
        if name:
            if country_code and f"({country_code.upper()})" not in name:
                display_name = f"{name} ({country_code.upper()})"
            else:
                display_name = name
            self._server_name_text.value = display_name

        if country_code:
            code_lower = country_code.lower()
            self._flag_img.src = f"https://flagcdn.com/w40/{code_lower}.png"
            self._flag_img.visible = True
        else:
            self._flag_img.src = "https://flagcdn.com/w40/fi.png"
            self._flag_img.visible = True

        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def update_internet_status(self, is_online: bool):
        """Update connection status."""
        self._is_online = is_online

    def update_uptime(self, uptime_str: str):
        """Update uptime timer text underneath central connection button."""
        self._uptime_text.value = uptime_str
        try:
            if hasattr(self, "_uptime_text") and self._uptime_text.page:
                self._uptime_text.update()
        except Exception:
            pass
