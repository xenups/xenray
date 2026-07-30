"""Logs & Telemetry View Component."""
from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors, create_glass_container


class LogsView(ft.Container):
    """Logs & Telemetry View based on Stitch specs."""

    def __init__(
        self,
        log_text_control: ft.Control,
        on_copy_logs_click: Callable,
        on_download_logs_click: Callable,
        on_clear_logs_click: Callable,
    ):
        self._log_text_control = log_text_control
        self._on_copy_logs_click = on_copy_logs_click
        self._on_download_logs_click = on_download_logs_click
        self._on_clear_logs_click = on_clear_logs_click

        # Diagnostic Stats Cards — updatable text references
        WHITE = ft.Colors.WHITE
        self._memory_value = ft.Text("--", size=18, weight=ft.FontWeight.W_700, color=WHITE)
        self._memory_bar = ft.ProgressBar(value=0, color=AppColors.SECONDARY, bgcolor=AppColors.SURFACE_CONTAINER_HIGH)
        self._threads_value = ft.Text("--", size=18, weight=ft.FontWeight.W_700, color=WHITE)
        self._threads_sub = ft.Text("", size=11, color=AppColors.PRIMARY)
        self._health_value = ft.Text("--", size=18, weight=ft.FontWeight.W_700, color=WHITE)
        self._health_sub = ft.Text("", size=11, color=AppColors.ON_SURFACE_VARIANT)

        self._memory_card = create_glass_container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.MEMORY, size=20, color=AppColors.SECONDARY),
                            ft.Text(t("logs.memory", default="Memory"), size=11, color=AppColors.ON_SURFACE_VARIANT),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self._memory_value,
                    self._memory_bar,
                ],
                spacing=8,
            ),
            expand=True,
        )

        self._threads_card = create_glass_container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SWAP_CALLS, size=20, color=AppColors.PRIMARY),
                            ft.Text(
                                t("logs.active_threads", default="Active Threads"),
                                size=11,
                                color=AppColors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self._threads_value,
                    self._threads_sub,
                ],
                spacing=8,
            ),
            expand=True,
        )

        self._health_card = create_glass_container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.VERIFIED_USER, size=20, color=AppColors.PRIMARY),
                            ft.Text(
                                t("logs.health_status", default="Health Status"),
                                size=11,
                                color=AppColors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self._health_value,
                    self._health_sub,
                ],
                spacing=8,
            ),
            expand=True,
        )

        # Terminal Header Controls
        self._copy_btn = ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CONTENT_COPY, size=14, color=WHITE),
                    ft.Text(t("logs.copy", default="Copy"), size=11, color=WHITE),
                ],
                spacing=4,
            ),
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
            on_click=self._on_copy_logs_click,
        )
        self._download_btn = ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.DOWNLOAD, size=14, color=WHITE),
                    ft.Text(t("logs.download", default="Download"), size=11, color=WHITE),
                ],
                spacing=4,
            ),
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
            on_click=self._on_download_logs_click,
        )
        self._clear_btn = ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.DELETE, size=14, color=WHITE),
                    ft.Text(t("logs.clear", default="Clear"), size=11, color=WHITE),
                ],
                spacing=4,
            ),
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
            on_click=self._on_clear_logs_click,
        )

        # Glass Terminal Window
        self._terminal_window = create_glass_container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        width=10, height=10, shape=ft.BoxShape.CIRCLE, bgcolor=AppColors.ERROR
                                    ),
                                    ft.Container(
                                        width=10, height=10, shape=ft.BoxShape.CIRCLE, bgcolor=AppColors.PRIMARY
                                    ),
                                    ft.Container(
                                        width=10, height=10, shape=ft.BoxShape.CIRCLE, bgcolor=AppColors.SECONDARY
                                    ),
                                    ft.Text(
                                        t("logs.terminal_title", default="XENRAY_CLI :: MAIN_LOGGER"),
                                        size=11,
                                        weight=ft.FontWeight.W_600,
                                        color=AppColors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                spacing=8,
                            ),
                            ft.Row(
                                [self._copy_btn, self._download_btn, self._clear_btn],
                                spacing=6,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)),
                    ft.Container(content=self._log_text_control, expand=True),
                ],
                spacing=8,
                expand=True,
            ),
            expand=True,
            padding=16,
        )

        super().__init__(
            content=ft.Column(
                [
                    ft.Row([self._memory_card, self._threads_card, self._health_card], spacing=12),
                    self._terminal_window,
                ],
                spacing=16,
                expand=True,
            ),
            padding=24,
            expand=True,
        )

    def update_memory(self, used_mb: float, total_mb: float):
        """Update memory usage card."""
        self._memory_value.value = f"{used_mb:.1f} / {total_mb:.0f} MB"
        ratio = used_mb / total_mb if total_mb > 0 else 0
        self._memory_bar.value = min(1.0, ratio)
        try:
            self._memory_card.update()
        except Exception:
            pass

    def update_threads(self, thread_count: int, status: str = ""):
        """Update active threads card."""
        self._threads_value.value = f"{thread_count} {t('logs.nodes', default='Nodes')}"
        self._threads_sub.value = status or t("logs.optimal_performance", default="Optimal Performance")
        try:
            self._threads_card.update()
        except Exception:
            pass

    def update_health(self, issues: int, message: str = ""):
        """Update health status card."""
        self._health_value.value = f"{issues} {t('logs.issues', default='Issues')}"
        self._health_sub.value = message or t("logs.system_healthy", default="System is healthy")
        try:
            self._health_card.update()
        except Exception:
            pass
