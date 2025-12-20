"""Monitoring Service - Handles periodic connection monitoring."""
import threading
import time
from typing import TYPE_CHECKING, Callable, Optional

from loguru import logger

from src.core.connection_manager import ConnectionManager
from src.core.i18n import t
from src.ui.handlers.connection_handler import ConnectionHandler
from src.utils.network_utils import NetworkUtils

if TYPE_CHECKING:
    from src.ui.components.toast import ToastManager


class MonitoringService:
    """Manages periodic monitoring of connection health."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        connection_handler: ConnectionHandler,
    ):
        self._connection_manager = connection_manager
        self._connection_handler = connection_handler
        self._ui_call: Optional[Callable] = None
        self._toast: Optional[ToastManager] = None
        self._monitoring_active = False
        self._monitoring_thread: threading.Thread = None
        self.is_running = False

    def setup(self, ui_updater: Callable, toast_manager):
        """Bind UI dependencies to the service."""
        self._ui_call = ui_updater
        self._toast = toast_manager

    def start_monitoring_loop(self):
        """Start the periodic monitoring loop (runs every 60s)."""
        if self._monitoring_active:
            return

        self._monitoring_active = True

        def _loop():
            """Monitoring loop that runs every 60 seconds."""
            while self._monitoring_active:
                try:
                    # Wait 60 seconds
                    time.sleep(60)

                    # Skip if not running
                    if not self.is_running:
                        continue

                    logger.debug("[MonitoringService] Running periodic check")

                    # Check internet connectivity
                    has_internet = NetworkUtils.check_internet_connectivity()

                    if not has_internet:
                        logger.warning("[MonitoringService] Internet connectivity lost")
                        self._toast.error(t("connection.internet_lost"), 5000)

                        # Disconnect
                        self._connection_manager.disconnect()
                        self._ui_call(self._connection_handler.reset_ui_disconnected)
                        continue

                    logger.debug("[MonitoringService] Internet check passed")

                except Exception as e:
                    logger.error(f"[MonitoringService] Monitoring error: {e}")

        self._monitoring_thread = threading.Thread(target=_loop, daemon=True)
        self._monitoring_thread.start()
        logger.info("[MonitoringService] Monitoring loop started")

    def stop_monitoring(self):
        """Stop the monitoring loop."""
        self._monitoring_active = False
        logger.info("[MonitoringService] Monitoring loop stopped")
