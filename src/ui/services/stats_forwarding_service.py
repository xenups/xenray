"""Stats Forwarding Service - periodically streams network and system telemetry to active view subcomponents."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import TYPE_CHECKING

import psutil

from src.core.event_bus import TOPIC_TELEMETRY_UPDATED, event_bus

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class StatsForwardingService:
    """Service handling background stats forwarding loops and status display wrapping."""

    def __init__(self, main_window: MainWindow, network_interval: float = 1.0) -> None:
        self._mw = main_window
        self._network_interval = network_interval
        self._session_dl_bytes: float = 0.0
        self._session_ul_bytes: float = 0.0
        self._was_running: bool = False
        self._last_tick_time: float = 0.0

    @staticmethod
    def _fmt_bytes(b: float) -> str:
        if b < 1024:
            return f"{b:.0f} B"
        if b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        if b < 1024 * 1024 * 1024:
            return f"{b / (1024 * 1024):.1f} MB"
        return f"{b / (1024 * 1024 * 1024):.2f} GB"

    def start(self) -> None:
        """Start async background forwarding tasks."""
        self._mw._page.run_task(self.forward_network_stats)
        self._mw._page.run_task(self.forward_system_stats)
        self.wrap_status_display()

    def publish_now(self) -> None:
        """Immediately compute and publish network telemetry without waiting for the interval."""
        try:
            is_running = getattr(self._mw, "_is_running", False)
            if not is_running or getattr(self._mw, "_nav_locked", False):
                return
            network_stats = getattr(self._mw, "_network_stats", None)
            if not network_stats:
                return

            stats = network_stats.get_stats()
            down_str = stats.get("download_speed", "0 B/s")
            total_bps = float(stats.get("total_bps", 0))

            dl_bps = total_bps * 0.6
            ul_bps = total_bps * 0.4

            dl_total_str = self._fmt_bytes(self._session_dl_bytes)
            ul_total_str = self._fmt_bytes(self._session_ul_bytes)

            event_bus.publish(
                TOPIC_TELEMETRY_UPDATED,
                {
                    "rate_str": down_str,
                    "upload_str": ul_total_str,
                    "download_str": dl_total_str,
                    "download_bps": dl_bps,
                    "upload_bps": ul_bps,
                    "total_bps": total_bps,
                    "download_total": dl_total_str,
                    "upload_total": ul_total_str,
                    "is_connected": is_running,
                },
            )
        except Exception:
            pass

    async def forward_network_stats(self) -> None:
        """Periodically forward network stats to active views."""
        self._last_tick_time = time.monotonic()

        while True:
            try:
                # Immediate first poll: update BEFORE sleeping so the first
                # telemetry lands the moment the task starts (during splash),
                # not after the first tick.
                is_running = getattr(self._mw, "_is_running", False)

                if is_running and not self._was_running:
                    self._session_dl_bytes = 0.0
                    self._session_ul_bytes = 0.0
                    self._last_tick_time = time.monotonic()
                elif (not is_running) and self._was_running:
                    # Connection just dropped — zero-reset the speed badges
                    # in-place so Download/Upload don't stay stuck on their last
                    # recorded values after the FSM reaches DISCONNECTED.
                    self._session_dl_bytes = 0.0
                    self._session_ul_bytes = 0.0
                    event_bus.publish(
                        TOPIC_TELEMETRY_UPDATED,
                        {
                            "rate_str": "0 B/s",
                            "upload_str": "0 B/s",
                            "download_str": "0 B/s",
                            "download_bps": 0.0,
                            "upload_bps": 0.0,
                            "total_bps": 0.0,
                            "download_total": "0 B",
                            "upload_total": "0 B",
                            "is_connected": False,
                        },
                    )
                self._was_running = is_running

                if not is_running or getattr(self._mw, "_nav_locked", False):
                    continue

                network_stats = getattr(self._mw, "_network_stats", None)
                if not network_stats:
                    continue

                stats = network_stats.get_stats()
                down_str = stats.get("download_speed", "0 B/s")
                total_bps = float(stats.get("total_bps", 0))

                dl_bps = total_bps * 0.6
                ul_bps = total_bps * 0.4

                now = time.monotonic()
                dt = max(0.0, now - self._last_tick_time) if self._last_tick_time > 0 else self._network_interval
                self._last_tick_time = now

                self._session_dl_bytes += dl_bps * dt
                self._session_ul_bytes += ul_bps * dt

                dl_total_str = self._fmt_bytes(self._session_dl_bytes)
                ul_total_str = self._fmt_bytes(self._session_ul_bytes)

                # Publish live telemetry over the EventBus. DashboardView and
                # StatisticsView subscribe to this topic and refresh their speed
                # cards / WaveVisualizer on every tick (UI-thread safe loop).
                event_bus.publish(
                    TOPIC_TELEMETRY_UPDATED,
                    {
                        "rate_str": down_str,
                        "upload_str": ul_total_str,
                        "download_str": dl_total_str,
                        "download_bps": dl_bps,
                        "upload_bps": ul_bps,
                        "total_bps": total_bps,
                        "download_total": dl_total_str,
                        "upload_total": ul_total_str,
                        "is_connected": is_running,
                    },
                )
            except Exception:
                pass
            finally:
                await asyncio.sleep(self._network_interval)

    async def forward_system_stats(self) -> None:
        """Periodically forward system stats (memory, threads, health) to LogsView."""
        while True:
            try:
                # Immediate first poll: update BEFORE sleeping so memory/threads/
                # health are pre-warmed during splash — the Logs page shows
                # fresh data the moment it is opened, never a delayed display.
                if self._mw._nav_locked:
                    continue
                process = psutil.Process()
                mem_info = process.memory_info()
                used_mb = mem_info.rss / (1024 * 1024)
                total_mb = psutil.virtual_memory().total / (1024 * 1024)
                thread_count = threading.active_count()
                health_issues = 0

                if hasattr(self._mw, "_stitch_logs_view") and self._mw._stitch_logs_view:
                    self._mw._stitch_logs_view.update_memory(used_mb, total_mb)
                    self._mw._stitch_logs_view.update_threads(thread_count)
                    self._mw._stitch_logs_view.update_health(health_issues)
            except Exception:
                pass
            finally:
                await asyncio.sleep(3.0)

    def wrap_status_display(self) -> None:
        """Wrap status_display set_step to forward step messages to active dashboard view."""
        if not self._mw._status_display:
            return
        sd = self._mw._status_display

        orig_set_step = sd.set_step

        def wrapped_set_step(msg):
            orig_set_step(msg)
            try:
                if hasattr(self._mw, "_stitch_dashboard_view") and self._mw._stitch_dashboard_view:
                    self._mw._stitch_dashboard_view.set_step(msg)
            except Exception:
                pass

        sd.set_step = wrapped_set_step
