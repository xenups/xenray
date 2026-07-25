"""Network Stats Handler - Manages network statistics polling and UI updates."""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

import flet as ft
import psutil

from src.core.logger import logger
from src.services.network_stats import NetworkStatsService


class NetworkStatsHandler:
    """Handles network statistics polling and UI updates."""

    def __init__(self, network_stats: NetworkStatsService):
        self._network_stats = network_stats
        self._page: Optional[ft.Page] = None
        self._status_display = None
        self._connection_button = None
        self._logs_drawer_component = None
        self._earth_glow = None
        self._logs_heartbeat = None
        self._heartbeat = None

        # State access required for logic
        self._is_running_getter: Optional[Callable[[], bool]] = None
        self._uptime_start: float = 0.0
        self._last_internet_check: float = 0.0
        self._is_online_cache: bool = True

    @staticmethod
    def _page_attached(control) -> bool:
        """Check if a control is mounted to the page (RuntimeError-safe)."""
        try:
            return control and control.page is not None
        except (RuntimeError, AttributeError):
            return False

    def setup(
        self,
        page: ft.Page,
        status_display,
        connection_button,
        logs_drawer_component,
        earth_glow,
        logs_heartbeat,
        heartbeat,
        is_running_getter: Callable[[], bool],
    ):
        """Bind UI components and state getters to the handler."""
        self._page = page
        self._status_display = status_display
        self._connection_button = connection_button
        self._logs_drawer_component = logs_drawer_component
        self._earth_glow = earth_glow
        self._logs_heartbeat = logs_heartbeat
        self._heartbeat = heartbeat
        self._is_running_getter = is_running_getter

    async def run_stats_loop(self):
        """
        Dedicated UI loop for network stats.
        Polls shared state from service and updates UI.
        Runs on main UI thread (Async), does NOT block.
        """
        while True:
            try:
                if not self._page:
                    await asyncio.sleep(1.0)
                    continue

                # Poll and update stats
                self._update_ui()

                # Poll interval: 1 second for responsive dashboard stats
                await asyncio.sleep(1.0)

            except Exception as e:
                logger.error(f"Error in stats UI loop: {e}")
                await asyncio.sleep(1.0)

    def update_ui_immediately(self):
        """Triggers an immediate UI update if possible."""
        try:
            if self._page:
                self._update_ui()
        except Exception as e:
            logger.debug(f"Immediate stats update skipped: {e}")

    def _update_ui(self):
        """Core logic to sync stats with UI components."""
        is_running = self._is_running_getter() if self._is_running_getter else False

        # Read Shared State from NetworkStatsService
        stats = self._network_stats.get_stats()

        down_str = stats.get("download_speed", "0.0 MB/s")
        up_str = stats.get("upload_speed", "0.0 MB/s")
        session_up = stats.get("session_upload", "0.0 MB")
        session_down = stats.get("session_download", "0.0 MB")

        try:
            total_bps = float(stats.get("total_bps", 0))
            download_bps = float(stats.get("download_bps", 0))
            upload_bps = float(stats.get("upload_bps", 0))
        except (ValueError, TypeError):
            total_bps = 0.0
            download_bps = 0.0
            upload_bps = 0.0

        mw = self._page._main_window if hasattr(self._page, "_main_window") else None

        # Check direct physical internet connection periodically (every 5s)
        now = asyncio.get_event_loop().time()
        if now - self._last_internet_check > 5.0:
            self._last_internet_check = now
            from src.utils.network_utils import NetworkUtils

            self._is_online_cache = NetworkUtils.check_internet_connection(timeout=1, retries=1)

        # Update Stitch DashboardView stats continuously
        if mw and hasattr(mw, "_stitch_dashboard_view") and mw._stitch_dashboard_view:
            view = mw._stitch_dashboard_view
            if view:
                view.update_internet_status(self._is_online_cache)
                view.update_network_stats(
                    rate_str=down_str if is_running else "0.0 MB/s",
                    upload_str=session_up,
                    download_str=session_down,
                    download_bps=download_bps if is_running else 0.0,
                    upload_bps=upload_bps if is_running else 0.0,
                    total_bps=total_bps if is_running else 0.0,
                )
                if is_running:
                    view.update_glow_intensity(total_bps)
        # Update LogsView diagnostic cards
        if mw and hasattr(mw, "_stitch_logs_view") and mw._stitch_logs_view:
            lv = mw._stitch_logs_view
            try:
                mem = psutil.virtual_memory()
                lv.update_memory(mem.used / (1024 * 1024), mem.total / (1024 * 1024))
            except Exception:
                pass
            try:
                cpu_count = psutil.cpu_count()
                status = "Optimal" if cpu_count > 0 else ""
                lv.update_threads(cpu_count, status)
            except Exception:
                pass
            try:
                mem_percent = psutil.virtual_memory().percent
                if mem_percent > 90:
                    lv.update_health(1, "High memory usage")
                else:
                    lv.update_health(0)
            except Exception:
                pass

        if not is_running:
            self._uptime_start = 0.0
            if self._heartbeat and self._page_attached(self._heartbeat) and self._heartbeat.opacity != 0:
                self._heartbeat.opacity = 0
                try:
                    self._heartbeat.update()
                except Exception:
                    pass
            return

        # Track uptime
        if self._uptime_start == 0.0:
            self._uptime_start = asyncio.get_event_loop().time()
        elapsed = int(asyncio.get_event_loop().time() - self._uptime_start)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if mw and hasattr(mw, "_stitch_dashboard_view") and mw._stitch_dashboard_view:
            mw._stitch_dashboard_view.update_uptime(uptime_str)

        # Update Connection Button Glow
        if self._connection_button and self._page_attached(self._connection_button):
            self._connection_button.update_network_activity(total_bps)

        # Update LogsDrawer stats if mounted
        if self._logs_drawer_component and self._page_attached(self._logs_drawer_component):
            self._logs_drawer_component.update_network_stats(down_str, up_str)

        # Heartbeat logic
        if self._logs_heartbeat and self._page_attached(self._logs_heartbeat):
            is_bright = self._logs_heartbeat.opacity > 0.5
            self._logs_heartbeat.opacity = 0.3 if is_bright else 1.0
            try:
                self._logs_heartbeat.update()
            except Exception:
                pass
