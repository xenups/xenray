"""Logger Controller - manages log stream state, buffer exporting, and telemetry metrics."""

from __future__ import annotations

from typing import NamedTuple

from src.core.i18n import t


class MemoryMetric(NamedTuple):
    """Formatted memory metric payload."""

    text: str
    ratio: float


class ThreadMetric(NamedTuple):
    """Formatted thread metric payload."""

    text: str
    status: str


class HealthMetric(NamedTuple):
    """Formatted health metric payload."""

    text: str
    message: str


class LoggerController:
    """Controller handling log view formatting and metric calculations."""

    @staticmethod
    def format_memory(used_mb: float, total_mb: float) -> MemoryMetric:
        """Format RAM usage text and progress ratio."""
        text = f"{used_mb:.1f} / {total_mb:.0f} MB"
        ratio = min(1.0, used_mb / total_mb) if total_mb > 0 else 0.0
        return MemoryMetric(text=text, ratio=ratio)

    @staticmethod
    def format_threads(thread_count: int, status: str = "") -> ThreadMetric:
        """Format active thread node text and performance label."""
        text = f"{thread_count} {t('logs.nodes', default='Nodes')}"
        status_label = status or t("logs.optimal_performance", default="Optimal Performance")
        return ThreadMetric(text=text, status=status_label)

    @staticmethod
    def format_health(issues: int, message: str = "") -> HealthMetric:
        """Format health status text and system health label."""
        text = f"{issues} {t('logs.issues', default='Issues')}"
        msg = message or t("logs.system_healthy", default="System is healthy")
        return HealthMetric(text=text, message=msg)
