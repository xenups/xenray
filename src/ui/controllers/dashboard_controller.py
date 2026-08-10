"""Dashboard Controller - manages connection state transitions, uptime timer, and traffic formatting."""

from __future__ import annotations

import enum
import threading
import time
from typing import Callable, Optional

from src.core.i18n import t
from src.core.logger import logger
from src.ui.helpers.status_helper import get_short_status_label


class DashboardState(enum.Enum):
    """Dashboard connection state enum."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"


class DashboardController:
    """Controller handling reactive state, uptime tracking, and throughput calculations for DashboardView."""

    def __init__(
        self,
        on_state_changed: Optional[Callable[[DashboardState, str], None]] = None,
        on_uptime_updated: Optional[Callable[[str], None]] = None,
        on_stats_updated: Optional[Callable[[str, str, float], None]] = None,
    ) -> None:
        self._state: DashboardState = DashboardState.DISCONNECTED
        self._on_state_changed = on_state_changed
        self._on_uptime_updated = on_uptime_updated
        self._on_stats_updated = on_stats_updated

        self._timer_running: bool = False
        self._start_time: float = 0.0
        self._timer_thread: Optional[threading.Thread] = None

    @property
    def state(self) -> DashboardState:
        """Current dashboard connection state."""
        return self._state

    def set_connection_state(
        self,
        is_connected: bool,
        is_connecting: bool = False,
        is_disconnecting: bool = False,
    ) -> None:
        """Transition dashboard connection state and trigger callbacks."""
        try:
            if is_disconnecting:
                self._state = DashboardState.DISCONNECTING
                label = get_short_status_label(t("app.disconnecting"))
                self.stop_uptime_timer()
            elif is_connecting:
                self._state = DashboardState.CONNECTING
                label = get_short_status_label(t("app.connecting"))
                if self._on_uptime_updated:
                    self._on_uptime_updated("00:00:00")
            elif is_connected:
                self._state = DashboardState.CONNECTED
                label = get_short_status_label(t("app.connected"))
                self.start_uptime_timer()
            else:
                self._state = DashboardState.DISCONNECTED
                label = get_short_status_label(t("app.disconnected"))
                self.stop_uptime_timer()

            if self._on_state_changed:
                self._on_state_changed(self._state, label)
        except Exception as e:
            logger.error(f"[DashboardController] Error setting connection state: {e}")

    def start_uptime_timer(self) -> None:
        """Start background timer loop for uptime tracking."""
        if self._timer_running:
            return
        self._timer_running = True
        self._start_time = time.time()

        def timer_loop() -> None:
            while self._timer_running and self._state == DashboardState.CONNECTED:
                try:
                    elapsed = int(time.time() - self._start_time)
                    hours = elapsed // 3600
                    minutes = (elapsed % 3600) // 60
                    seconds = elapsed % 60
                    uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    if self._on_uptime_updated:
                        self._on_uptime_updated(uptime_str)
                except Exception as e:
                    logger.debug(f"[DashboardController] Uptime timer loop error: {e}")
                    break
                time.sleep(1.0)

        self._timer_thread = threading.Thread(target=timer_loop, daemon=True)
        self._timer_thread.start()

    def stop_uptime_timer(self) -> None:
        """Stop background uptime timer loop."""
        self._timer_running = False

    def process_network_stats(
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
    ) -> None:
        """Process throughput rates into formatted strings and trigger updates."""
        try:
            dl_text = (
                speed_text
                if speed_text is not None
                else (download_total if download_total is not None else download_str)
            )
            if dl_text == "0.0 MB" and rate_str != "0.0 MB/s":
                dl_text = rate_str

            ul_text = upload_total if upload_total is not None else upload_str
            if ul_text == "0.0 MB" and upload_bps > 0:
                ul_speed_kb = upload_bps / 1024.0
                ul_text = f"{ul_speed_kb:.1f} KB/s" if ul_speed_kb < 1024.0 else f"{(ul_speed_kb / 1024.0):.1f} MB/s"

            active_total_bps = total_bps if total_bps > 0 else (download_bps + upload_bps)
            if self._on_stats_updated:
                self._on_stats_updated(dl_text, ul_text, active_total_bps)
        except Exception as e:
            logger.error(f"[DashboardController] Error processing network stats: {e}")
