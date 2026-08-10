"""Stats Forwarding Service - periodically streams network and system telemetry to active view subcomponents."""

from __future__ import annotations

import asyncio
import os
import threading
from typing import TYPE_CHECKING

import psutil

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
                await asyncio.sleep(_interval)
                is_running = self._mw._is_running

                if is_running and not _was_running:
                    _session_dl_bytes = 0.0
                    _session_ul_bytes = 0.0
                _was_running = is_running

                if not is_running or self._mw._nav_locked:
                    continue

                stats = self._mw._network_stats.get_stats()
                down_str = stats.get("download_speed", "0 B/s")
                up_str = stats.get("upload_speed", "0 B/s")
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

                kwargs = dict(
                    rate_str=down_str,
                    upload_str=ul_total_str,
                    download_str=dl_total_str,
                    download_bps=dl_bps,
                    upload_bps=ul_bps,
                    total_bps=total_bps,
                    download_total=dl_total_str,
                    upload_total=ul_total_str,
                )

                if (
                    self._mw._active_tab == "dashboard"
                    and hasattr(self._mw, "_stitch_dashboard_view")
                    and self._mw._stitch_dashboard_view
                ):
                    self._mw._stitch_dashboard_view.update_network_stats(**kwargs)
                elif (
                    self._mw._active_tab == "statistics"
                    and hasattr(self._mw, "_stitch_statistics_view")
                    and self._mw._stitch_statistics_view
                ):
                    self._mw._stitch_statistics_view.update_network_stats(**kwargs)
            except Exception:
                pass

    async def forward_system_stats(self) -> None:
        """Periodically forward system stats (memory, threads, health) to LogsView."""
        while True:
            try:
                await asyncio.sleep(3.0)
                if self._mw._nav_locked:
                    continue
                if self._mw._active_tab != "logs":
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

    def wrap_status_display(self) -> None:
        """Wrap status_display methods to forward step messages to dashboard view."""
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

        orig_set_connecting = sd.set_connecting

        def wrapped_set_connecting():
            orig_set_connecting()
            try:
                if hasattr(self._mw, "_stitch_dashboard_view") and self._mw._stitch_dashboard_view:
                    self._mw._stitch_dashboard_view.set_connection_state(is_connected=False, is_connecting=True)
            except Exception:
                pass

        sd.set_connecting = wrapped_set_connecting

        orig_set_connected = sd.set_connected

        def wrapped_set_connected(country_data=None):
            orig_set_connected(country_data)
            try:
                if hasattr(self._mw, "_stitch_dashboard_view") and self._mw._stitch_dashboard_view:
                    self._mw._stitch_dashboard_view.set_connection_state(is_connected=True)
            except Exception:
                pass

        sd.set_connected = wrapped_set_connected

        orig_set_disconnected = sd.set_disconnected

        def wrapped_set_disconnected():
            orig_set_disconnected()
            try:
                if hasattr(self._mw, "_stitch_dashboard_view") and self._mw._stitch_dashboard_view:
                    self._mw._stitch_dashboard_view.set_connection_state(is_connected=False)
            except Exception:
                pass

        sd.set_disconnected = wrapped_set_disconnected

        orig_set_disconnecting = sd.set_disconnecting

        def wrapped_set_disconnecting():
            orig_set_disconnecting()
            try:
                if hasattr(self._mw, "_stitch_dashboard_view") and self._mw._stitch_dashboard_view:
                    self._mw._stitch_dashboard_view.set_connection_state(is_connected=False, is_disconnecting=True)
            except Exception:
                pass

        sd.set_disconnecting = wrapped_set_disconnecting
