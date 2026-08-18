"""Stats Forwarding Service - periodically streams network and system telemetry to active view subcomponents."""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

import psutil

from src.core.event_bus import TOPIC_TELEMETRY_UPDATED, event_bus

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class StatsForwardingService:
    """Service handling background stats forwarding loops and status display wrapping."""

    def __init__(self, main_window: MainWindow) -> None:
        self._mw = main_window

    def start(self) -> None:
        """Start async background forwarding tasks."""
        self._mw._page.run_task(self.forward_network_stats)
        self._mw._page.run_task(self.forward_system_stats)
        self.wrap_status_display()

    async def forward_network_stats(self) -> None:
        """Periodically forward network stats to active views."""
        _session_dl_bytes: float = 0.0
        _session_ul_bytes: float = 0.0
        _was_running: bool = False
        _interval: float = 3.0

        while True:
            try:
                # Immediate first poll: update BEFORE sleeping so the first
                # telemetry lands the moment the task starts (during splash),
                # not after the first 3s tick.
                is_running = self._mw._is_running

                if is_running and not _was_running:
                    _session_dl_bytes = 0.0
                    _session_ul_bytes = 0.0
                elif (not is_running) and _was_running:
                    # Connection just dropped — zero-reset the speed badges
                    # in-place so Download/Upload don't stay stuck on their last
                    # recorded values after the FSM reaches DISCONNECTED.
                    _session_dl_bytes = 0.0
                    _session_ul_bytes = 0.0
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
                _was_running = is_running

                if not is_running or self._mw._nav_locked:
                    continue

                stats = self._mw._network_stats.get_stats()
                down_str = stats.get("download_speed", "0 B/s")
                total_bps = float(stats.get("total_bps", 0))

                dl_bps = total_bps * 0.6
                ul_bps = total_bps * 0.4

                _session_dl_bytes += dl_bps * _interval
                _session_ul_bytes += ul_bps * _interval

                def _fmt_bytes(b: float) -> str:
                    if b < 1024:
                        return f"{b:.0f} B"
                    if b < 1024 * 1024:
                        return f"{b / 1024:.1f} KB"
                    if b < 1024 * 1024 * 1024:
                        return f"{b / (1024 * 1024):.1f} MB"
                    return f"{b / (1024 * 1024 * 1024):.2f} GB"

                dl_total_str = _fmt_bytes(_session_dl_bytes)
                ul_total_str = _fmt_bytes(_session_ul_bytes)

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
                await asyncio.sleep(_interval)

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
