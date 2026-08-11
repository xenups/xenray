"""Dashboard Controller - manages connection state transitions, uptime timer, and traffic formatting."""

from __future__ import annotations

import enum
import threading
import time
from typing import Callable, Optional

from src.core.i18n import t
from src.core.logger import logger
from src.ui.helpers.status_helper import get_short_status_label
from src.utils.formatting import format_speed


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
        self._timer_lock = threading.Lock()

    @property
    def state(self) -> DashboardState:
        """Current dashboard connection state."""
        return self._state

    def set_connection_state(
        self,
        is_connected: bool,
        is_connecting: bool = False,
        is_disconnecting: bool = False,
        connected_at: Optional[float] = None,
    ) -> None:
        """Transition dashboard connection state and trigger callbacks.

        Re-entrant emissions of the SAME target state are deduplicated so the
        button/status text renders exactly once per transition (the connecting
        state is pushed both by the handler's ``_set_connecting`` sync and the
        EventBus ``connecting`` event from the connection manager).
        """
        try:
            if is_disconnecting:
                target = DashboardState.DISCONNECTING
                label = get_short_status_label(t("app.disconnecting"))
            elif is_connecting:
                target = DashboardState.CONNECTING
                label = get_short_status_label(t("app.connecting"))
            elif is_connected:
                target = DashboardState.CONNECTED
                label = get_short_status_label(t("app.connected"))
            else:
                target = DashboardState.DISCONNECTED
                label = get_short_status_label(t("app.disconnected"))

            old_state = self._state

            if target == DashboardState.CONNECTED:
                self._state = target
                if old_state != DashboardState.CONNECTED or not self._timer_running:
                    self.start_uptime_timer(connected_at=connected_at)
            elif target == DashboardState.CONNECTING:
                self.stop_uptime_timer()
                if self._on_uptime_updated:
                    self._on_uptime_updated("00:00:00")
                self._state = target
            else:
                self.stop_uptime_timer()
                if self._on_uptime_updated:
                    self._on_uptime_updated("00:00:00")
                self._state = target

            if target == old_state:
                return

            if self._on_state_changed:
                self._on_state_changed(self._state, label)
        except Exception as e:
            logger.error(f"[DashboardController] Error setting connection state: {e}")

    def start_uptime_timer(self, connected_at: Optional[float] = None) -> None:
        """Start background timer loop for uptime tracking."""
        with self._timer_lock:
            if self._timer_running and self._timer_thread and self._timer_thread.is_alive():
                if connected_at and connected_at > 0:
                    self._start_time = connected_at
                return

            self._timer_running = True
            self._start_time = connected_at if (connected_at and connected_at > 0) else time.time()

            def timer_loop() -> None:
                while self._timer_running and self._state == DashboardState.CONNECTED:
                    try:
                        elapsed = max(0, int(time.time() - self._start_time))
                        hours, remainder = divmod(elapsed, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        if self._on_uptime_updated:
                            self._on_uptime_updated(uptime_str)
                        try:
                            from src.core.event_bus import event_bus

                            event_bus.publish("uptime_updated", {"uptime_str": uptime_str, "elapsed_seconds": elapsed})
                        except Exception:
                            pass
                    except Exception as e:
                        logger.debug(f"[DashboardController] Uptime timer tick error: {e}")
                    time.sleep(1.0)

            self._timer_thread = threading.Thread(target=timer_loop, daemon=True)
            self._timer_thread.start()

    def stop_uptime_timer(self) -> None:
        """Stop background uptime timer loop."""
        with self._timer_lock:
            self._timer_running = False
            self._timer_thread = None

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
            elif dl_text == "0.0 MB" and download_bps > 0:
                dl_text = format_speed(download_bps)

            ul_text = upload_total if upload_total is not None else upload_str
            if ul_text == "0.0 MB" and upload_bps > 0:
                ul_text = format_speed(upload_bps)

            active_total_bps = total_bps if total_bps > 0 else (download_bps + upload_bps)
            if self._on_stats_updated:
                self._on_stats_updated(dl_text, ul_text, active_total_bps)
        except Exception as e:
            logger.error(f"[DashboardController] Error processing network stats: {e}")
