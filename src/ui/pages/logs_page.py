"""Logs & Telemetry Page Component - unified height & flex alignment for top cards."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.components.dashboard.metric_card import MetricCard
from src.ui.components.logs import TerminalWindow
from src.ui.controllers.logger_controller import LoggerController
from src.ui.theme import AppColors


class LogsPage(ft.Container):
    """Logs & Telemetry Page based on Stitch specs."""

    def __init__(
        self,
        log_text_control: ft.Control,
        on_copy_logs_click: Callable,
        on_clear_logs_click: Callable,
        on_toggle_tailing: Callable | None = None,
    ):
        super().__init__()
        self.expand = True
        self.padding = 24

        self._log_text_control = log_text_control
        self._on_copy_logs_click = on_copy_logs_click
        self._on_clear_logs_click = on_clear_logs_click

        WHITE = ft.Colors.WHITE
        self._memory_value = ft.Text("--", size=14, weight=ft.FontWeight.W_600, color=WHITE)
        self._memory_bar = ft.ProgressBar(
            value=0,
            height=4,
            color=AppColors.SECONDARY,
            bgcolor=AppColors.SURFACE_CONTAINER_HIGH,
        )
        self._threads_value = ft.Text("--", size=14, weight=ft.FontWeight.W_600, color=WHITE)
        self._threads_sub = ft.Text("", size=11, color=AppColors.PRIMARY)
        self._health_value = ft.Text("--", size=14, weight=ft.FontWeight.W_600, color=WHITE)
        self._health_sub = ft.Text("", size=11, color=AppColors.ON_SURFACE_VARIANT)

        self._controller = LoggerController()

        self._memory_card = MetricCard(
            icon=ft.Icons.MEMORY,
            icon_color=AppColors.SECONDARY,
            title=t("logs.memory", default="Memory"),
            value_control=self._memory_value,
            footer_control=self._memory_bar,
            height=110,
            padding=14,
            expand=1,
        )

        self._threads_card = MetricCard(
            icon=ft.Icons.SWAP_CALLS,
            icon_color="#38BDF8",
            title=t("logs.active_threads", default="Active Threads"),
            value_control=self._threads_value,
            footer_control=self._threads_sub,
            height=110,
            padding=14,
            expand=1,
        )

        self._health_card = MetricCard(
            icon=ft.Icons.VERIFIED_USER,
            icon_color="#34D399",
            title=t("logs.health_status", default="Health Status"),
            value_control=self._health_value,
            footer_control=self._health_sub,
            height=110,
            padding=14,
            expand=1,
        )

        top_metrics_row = ft.Row(
            controls=[
                self._memory_card,
                self._threads_card,
                self._health_card,
            ],
            spacing=12,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self._terminal_window = TerminalWindow(
            log_text_control=self._log_text_control,
            on_copy_click=self._on_copy_logs_click,
            on_clear_click=self._on_clear_logs_click,
            on_toggle_tailing=on_toggle_tailing,
        )

        self.content = ft.Column(
            [
                top_metrics_row,
                self._terminal_window,
            ],
            spacing=12,
            expand=True,
        )

    def update_memory(self, used_mb: float, total_mb: float) -> None:
        """Update memory usage card."""
        try:
            metric = self._controller.format_memory(used_mb, total_mb)
            self._memory_value.value = metric.text
            self._memory_bar.value = metric.ratio
            if self._memory_card.page:
                self._memory_card.update()
        except Exception:
            pass

    def update_threads(self, thread_count: int, status: str = "") -> None:
        """Update active threads card."""
        try:
            metric = self._controller.format_threads(thread_count, status)
            self._threads_value.value = metric.text
            self._threads_sub.value = metric.status
            if self._threads_card.page:
                self._threads_card.update()
        except Exception:
            pass

    def update_health(self, issues: int, message: str = "") -> None:
        """Update health status card."""
        try:
            metric = self._controller.format_health(issues, message)
            self._health_value.value = metric.text
            self._health_sub.value = metric.message
            if self._health_card.page:
                self._health_card.update()
        except Exception:
            pass


# Backward-compatibility alias
LogsView = LogsPage
