"""Auto-Reconnect Service - Handles passive failure recovery."""

import threading
import time
from typing import Callable, Optional

from loguru import logger


class AutoReconnectService:
    """
    Handles automatic reconnection when passive monitoring detects failures.
    
    Responsibilities:
    - Verify internet availability
    - Check if Xray has self-recovered
    - Coordinate reconnection attempts
    - Emit events for UI notification
    """

    STABILIZATION_BUFFER = 2.0  # seconds to wait before reconnect

    def __init__(
        self,
        network_validator,
        config_loader: Callable[[str], tuple],
        connection_tester,
        connect_fn: Callable[[str, str], bool],
        event_emitter: Callable[[str, dict], None],
    ):
        """
        Initialize AutoReconnectService.
        
        Args:
            network_validator: Service to check internet connectivity
            config_loader: Function to load config from file path -> (config, error)
            connection_tester: ConnectionTester class/instance for health checks
            connect_fn: Function to establish connection (file_path, mode) -> success
            event_emitter: Function to emit events (event_type, data)
        """
        self._network_validator = network_validator
        self._config_loader = config_loader
        self._connection_tester = connection_tester
        self._connect_fn = connect_fn
        self._event_emitter = event_emitter
        self._lock = threading.Lock()

    def handle_failure(self, current_connection: Optional[dict]) -> bool:
        """
        Handle a detected connection failure.
        
        Args:
            current_connection: Current connection info dict with 'file' and 'mode' keys
            
        Returns:
            True if reconnection succeeded, False otherwise
        """
        logger.warning("[AutoReconnectService] Handling passive failure")
        self._emit("failure_detected")

        # 1. Check internet availability
        if not self._network_validator.check_internet_connection():
            logger.warning("[AutoReconnectService] Internet is offline")
            self._emit("reconnect_failed", {"reason": "no_internet"})
            return False

        # 2. Stabilization buffer
        logger.info(f"[AutoReconnectService] Waiting {self.STABILIZATION_BUFFER}s for stabilization...")
        time.sleep(self.STABILIZATION_BUFFER)

        # 3. Check if Xray recovered
        if current_connection:
            file_path = current_connection.get("file")
            if file_path and file_path != "Adopted Connection":
                if self._check_xray_recovered(file_path):
                    logger.info("[AutoReconnectService] Xray recovered, aborting reconnect")
                    self._emit("reconnected")  # Notify UI connection is restored
                    return True

        # 4. Attempt reconnect
        return self._attempt_reconnect(current_connection)

    def _check_xray_recovered(self, file_path: str) -> bool:
        """Check if Xray has self-recovered by testing connectivity."""
        try:
            config, _ = self._config_loader(file_path)
            if config:
                logger.debug("[AutoReconnectService] Testing if Xray recovered...")
                success, latency, _ = self._connection_tester.test_connection_sync(config)
                if success:
                    logger.info(f"[AutoReconnectService] Xray recovered (latency: {latency})")
                    return True
        except Exception as e:
            logger.warning(f"[AutoReconnectService] Could not verify recovery: {e}")
        return False

    def _attempt_reconnect(self, current_connection: Optional[dict]) -> bool:
        """Attempt to reconnect using stored connection info."""
        if not current_connection:
            logger.warning("[AutoReconnectService] No connection info available")
            self._emit("reconnect_failed", {"reason": "no_connection"})
            return False

        file_path = current_connection.get("file")
        mode = current_connection.get("mode")

        if not file_path or not mode or file_path == "Adopted Connection":
            logger.warning("[AutoReconnectService] Invalid connection info")
            self._emit("reconnect_failed", {"reason": "invalid_connection"})
            return False

        logger.info("[AutoReconnectService] Attempting reconnect...")
        self._emit("reconnecting")

        success = self._connect_fn(file_path, mode)

        if success:
            logger.info("[AutoReconnectService] Reconnect successful")
            self._emit("reconnected")
        else:
            logger.error("[AutoReconnectService] Reconnect failed")
            self._emit("reconnect_failed", {"reason": "connect_failed"})

        return success

    def _emit(self, event_type: str, data: dict = None):
        """Emit an event to the listener."""
        if self._event_emitter:
            try:
                self._event_emitter(event_type, data or {})
            except Exception as e:
                logger.error(f"[AutoReconnectService] Error emitting event: {e}")
