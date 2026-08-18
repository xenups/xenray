"""Statistics Page Component - Dedicated Network Statistics and Wave Chart Analytics Page."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.event_bus import TOPIC_TELEMETRY_UPDATED, event_bus
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
        # True only after the FIRST real telemetry event has rendered real data
        # (never when a synthetic all-zero payload arrives). Until then the page
        # shows the empty-state hint / "—" placeholders instead of fake zeros.
        self._has_data = False

        WHITE = ft.Colors.WHITE
        PURPLE = AppColors.PRIMARY
        CYAN = ft.Colors.CYAN_400

        self._controller = StatisticsController(history_size=16, num_bars=32)

        # Set by NavigationService on tab changes so telemetry rendering (and the
        # wave bar animations) pause completely while this page is hidden.
        self._is_visible = False

        event_bus.subscribe(TOPIC_TELEMETRY_UPDATED, self._on_telemetry_event)

        # "—" placeholders until the first real telemetry payload arrives — the
        # page must never present fake "0.0 MB/s" values while waiting for data.
        self._rate_text_control = ft.Text("—", size=13, weight=ft.FontWeight.W_700, color=WHITE)
        self._rate_header = StatsHeader(rate_text_control=self._rate_text_control)

        self._dl_speed_text = ft.Text("—", size=18, weight=ft.FontWeight.W_700, color=WHITE)
        self._ul_speed_text = ft.Text("—", size=18, weight=ft.FontWeight.W_700, color=WHITE)
        self._dl_total_text = ft.Text("—", size=11, weight=ft.FontWeight.W_600, color=WHITE)
        self._ul_total_text = ft.Text("—", size=11, weight=ft.FontWeight.W_600, color=WHITE)
        self._total_transfer_text = ft.Text("—", size=18, weight=ft.FontWeight.W_700, color=CYAN)
        self._peak_speed_text = ft.Text("—", size=11, weight=ft.FontWeight.W_600, color=WHITE)

        self._dl_card = StatCard(
            title=t("dashboard.download", default="Download Speed"),
            val_control=self._dl_speed_text,
            sub_title=t("stats.session", default="Session: "),
            sub_val_control=self._dl_total_text,
            icon=ft.Icons.SOUTH_WEST_ROUNDED,
            icon_color=PURPLE,
        )

        self._ul_card = StatCard(
            title=t("dashboard.upload", default="Upload Speed"),
            val_control=self._ul_speed_text,
            sub_title=t("stats.session", default="Session: "),
            sub_val_control=self._ul_total_text,
            icon=ft.Icons.NORTH_EAST_ROUNDED,
            icon_color=CYAN,
        )

        self._total_card = StatCard(
            title=t("stats.total_data", default="Total Data Transfer"),
            val_control=self._total_transfer_text,
            sub_title=t("stats.peak_speed", default="Peak Speed: "),
            sub_val_control=self._peak_speed_text,
            icon=ft.Icons.SWAP_VERT_ROUNDED,
            icon_color="#a855f7",
        )

        self._cards_row = ft.Row(
            [self._dl_card, self._ul_card, self._total_card],
            spacing=12,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self._wave_chart = WaveVisualizer(num_bars=32)
        self._wave_card = WaveCard(wave_chart=self._wave_chart)

        content_column = ft.Column(
            [self._rate_header, self._cards_row, self._wave_card],
            spacing=16,
            expand=True,
        )

        super().__init__(
            content=ft.WindowDragArea(
                content=ft.Container(content=content_column, expand=True),
                expand=True,
            ),
            padding=20,
            expand=True,
            bgcolor=ft.Colors.TRANSPARENT,
        )

    def dispose(self) -> None:
        """Release EventBus subscriptions held by this view."""
        event_bus.unsubscribe(TOPIC_TELEMETRY_UPDATED, self._on_telemetry_event)

    def set_visible(self, visible: bool) -> None:
        """Mark the page as shown/hidden so telemetry rendering can pause."""
        self._is_visible = visible

    def _on_telemetry_event(self, data) -> None:
        """Handle telemetry_updated EventBus events (published on the UI event loop)."""
        if not isinstance(data, dict):
            return
        try:
            # Synthetic zero-reset payloads (broadcast by the forwarding service
            # when the connection drops) must NOT count as real data — they
            # would hide the empty-state behind fake "0.0 MB/s" values.
            has_data = bool(data.get("is_connected", self._is_connected)) or any(
                float(data.get(k, 0.0)) > 0.0 for k in ("download_bps", "upload_bps", "total_bps")
            )
            self.update_network_stats(
                rate_str=data.get("rate_str", "—"),
                download_bps=float(data.get("download_bps", 0.0)),
                upload_bps=float(data.get("upload_bps", 0.0)),
                total_bps=float(data.get("total_bps", 0.0)),
                upload_total=data.get("upload_total"),
                download_total=data.get("download_total"),
                _has_data=has_data,
            )
        except Exception:
            pass

    def set_connection_state(
        self,
        is_connected: bool,
        is_connecting: bool = False,
        is_disconnecting: bool = False,
    ) -> None:
        self._is_connected = is_connected
        if not is_connected and not is_connecting:
            self._controller.reset()
            self._wave_card.reset_heights()
            # Disconnected: drop the stale-data flag so values reset to
            # placeholders (no fake zeros behind).
            self._has_data = False
            self._reset_placeholders()

    def update_server_info(self, *args, **kwargs) -> None:
        """No-op: server details are presented by ServerCard components."""

    def update_network_stats(
        self,
        rate_str: str = "0.0 MB/s",
        upload_str: str = "0.0 MB",
        download_str: str = "0.0 MB",
        download_bps: float = 0.0,
        upload_bps: float = 0.0,
        total_bps: float = 0.0,
        speed_text: Optional[str] = None,
        upload_total: Optional[str] = None,
        download_total: Optional[str] = None,
        _has_data: Optional[bool] = None,
    ) -> None:
        # The first REAL telemetry payload switches the page into live
        # statistics view. Synthetic all-zero payloads never flip this flag.
        if _has_data is not None and _has_data:
            self._has_data = True

        # Keep placeholders while disconnected / awaiting first data (no fake
        # zeros). With real data the flag above just flipped on.
        if not self._has_data or not self._is_connected:
            return

        payload = self._controller.process_stats(
            is_connected=self._is_connected,
            download_bps=download_bps,
            upload_bps=upload_bps,
            total_bps=total_bps,
            rate_str=rate_str,
            upload_str=upload_str,
            download_str=download_str,
            speed_text=speed_text,
            upload_total=upload_total,
            download_total=download_total,
        )

        if payload is None:
            return

        # Keep controller history flowing while hidden (so the wave resumes
        # smoothly on re-entry) but skip all rendering + bar animation when the
        # page isn't visible — zero CPU/GPU cycles are spent on hidden bars.
        if not self._is_visible:
            return

        self._rate_header.update_rate(payload.rate_str)
        self._dl_card.update_telemetry(payload.dl_speed_str, payload.download_str)
        self._ul_card.update_telemetry(payload.ul_speed_str, payload.upload_str)
        self._total_card.update_telemetry(payload.total_transfer_str, payload.peak_speed_str)
        self._wave_card.update_telemetry(payload.dl_heights, payload.ul_heights)

    def _reset_placeholders(self) -> None:
        """Restore the "—" placeholders (disconnect path)."""
        self._rate_text_control.value = "—"
        self._dl_speed_text.value = "—"
        self._ul_speed_text.value = "—"
        self._dl_total_text.value = "—"
        self._ul_total_text.value = "—"
        self._total_transfer_text.value = "—"
        self._peak_speed_text.value = "—"
        try:
            self.update()
        except Exception:
            pass


# Backward compatibility alias
StatisticsView = StatisticsPage
