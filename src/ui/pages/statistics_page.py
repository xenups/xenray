"""Statistics Page Component - Dedicated Network Statistics and Wave Chart Analytics Page."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import t
from src.ui.components.dashboard.wave_visualizer import WaveVisualizer
from src.ui.components.statistics import StatCard, StatsHeader, WaveCard
from src.ui.controllers.statistics_controller import StatisticsController
from src.ui.theme import AppColors


class StatisticsPage(ft.Container):
    """Fluent Integrated Statistics Page with high-density wave chart, speed cards, and data transfer analytics."""

    def __init__(self, on_back_click: Optional[Callable] = None):
        self._on_back_click = on_back_click
        self._is_connected = False
        self._is_online = True

        WHITE = ft.Colors.WHITE
        PURPLE = AppColors.PRIMARY
        CYAN = ft.Colors.CYAN_400

        self._controller = StatisticsController(history_size=16, num_bars=32)

        self._rate_text_control = ft.Text("0.0 MB/s", size=13, weight=ft.FontWeight.W_700, color=WHITE)
        top_header_row = StatsHeader(rate_text_control=self._rate_text_control)

        self._dl_speed_text = ft.Text("0.0 MB/s", size=18, weight=ft.FontWeight.W_700, color=WHITE)
        self._ul_speed_text = ft.Text("0.0 MB/s", size=18, weight=ft.FontWeight.W_700, color=WHITE)
        self._dl_total_text = ft.Text("0.0 MB", size=11, weight=ft.FontWeight.W_600, color=WHITE)
        self._ul_total_text = ft.Text("0.0 MB", size=11, weight=ft.FontWeight.W_600, color=WHITE)
        self._total_transfer_text = ft.Text("0.0 MB / 0.0 MB", size=18, weight=ft.FontWeight.W_700, color=CYAN)
        self._uptime_display_text = ft.Text("00:00:00", size=11, weight=ft.FontWeight.W_600, color=WHITE)
        self._peak_speed_text = ft.Text("0.0 MB/s", size=11, weight=ft.FontWeight.W_600, color=WHITE)

        card_dl_speed = StatCard(
            title=t("dashboard.download", default="Download Speed"),
            val_control=self._dl_speed_text,
            sub_title=t("stats.session", default="Session: "),
            sub_val_control=self._dl_total_text,
            icon=ft.Icons.SOUTH_WEST_ROUNDED,
            icon_color=PURPLE,
        )

        card_ul_speed = StatCard(
            title=t("dashboard.upload", default="Upload Speed"),
            val_control=self._ul_speed_text,
            sub_title=t("stats.session", default="Session: "),
            sub_val_control=self._ul_total_text,
            icon=ft.Icons.NORTH_EAST_ROUNDED,
            icon_color=CYAN,
        )

        card_total_stats = StatCard(
            title=t("stats.total_data", default="Total Data Transfer"),
            val_control=self._total_transfer_text,
            sub_title=t("stats.peak_speed", default="Peak Speed: "),
            sub_val_control=self._peak_speed_text,
            icon=ft.Icons.SWAP_VERT_ROUNDED,
            icon_color="#a855f7",
        )

        cards_row = ft.Row(
            [card_dl_speed, card_ul_speed, card_total_stats],
            spacing=12,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self._wave_chart = WaveVisualizer(num_bars=32)
        visualizer_card = WaveCard(wave_chart=self._wave_chart)

        content_column = ft.Column(
            [top_header_row, cards_row, visualizer_card],
            spacing=16,
            expand=True,
        )

        super().__init__(
            content=ft.WindowDragArea(content=content_column, expand=True),
            padding=20,
            expand=True,
            bgcolor=ft.Colors.TRANSPARENT,
        )

    def set_connection_state(
        self,
        is_connected: bool,
        is_connecting: bool = False,
    ) -> None:
        self._is_connected = is_connected
        if not is_connected and not is_connecting:
            self._controller.reset()
            self._wave_chart.reset_heights()

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
    ) -> None:
        payload = self._controller.process_stats(
            is_connected=self._is_connected,
            download_bps=download_bps,
            upload_bps=upload_bps,
            total_bps=total_bps,
            rate_str=rate_str,
            upload_str=upload_str,
            download_str=download_str,
        )

        if payload is None:
            return

        self._rate_text_control.value = payload.rate_str
        self._dl_speed_text.value = payload.dl_speed_str
        self._ul_speed_text.value = payload.ul_speed_str
        self._dl_total_text.value = payload.download_str
        self._ul_total_text.value = payload.upload_str
        self._total_transfer_text.value = payload.total_transfer_str
        self._peak_speed_text.value = payload.peak_speed_str

        self._wave_chart.set_network_activity(payload.activity)

        try:
            if self.page:
                self.update()
        except Exception:
            pass


# Backward compatibility alias
StatisticsView = StatisticsPage
