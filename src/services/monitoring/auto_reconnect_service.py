"""Auto-Reconnect Service - Handles passive failure recovery with session scoping."""

import threading
from typing import Callable, Optional

from loguru import logger


class AutoReconnectService:
    """
    Handles automatic reconnection when passive monitoring detects failures.

    Session-Scoped Design:
    - Each connection has a unique session_id
    - All operations validate against current session
    - Disconnect invalidates session, causing immediate cancellation
    - No stale events can be emitted after session invalidation

    State Guarantees:
    - Disconnect is terminal: no automatic restart possible
    - Cancellation is checked at every checkpoint
    - Events are only emitted if session is still valid
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

        # Session-scoped cancellation
        self._session_id = 0  # Incremented on each new connection
        self._cancel_event = threading.Event()
        self._cancelled = False

    def start_session(self, session_id: int):
        """
        Start a new connection session with the provided session ID.

        Args:
            session_id: Session ID from ConnectionManager
        """
        with self._lock:
            self._session_id = session_id
            self._cancelled = False
            self._cancel_event.clear()
            logger.debug(f"[AutoReconnectService] Started session {self._session_id}")

    def cancel(self):
        """
        Cancel any in-progress reconnect attempt immediately.

        This is a HARD override - no reconnect or event emission after this.
        Called by disconnect() to ensure terminal state.
        """
        with self._lock:
            self._cancelled = True
            self._cancel_event.set()
            logger.info(f"[AutoReconnectService] Session {self._session_id} cancelled (hard override)")

    def is_cancelled(self) -> bool:
        """Check if current session is cancelled."""
        with self._lock:
            return self._cancelled

    def handle_failure(self, current_connection: Optional[dict], session_id: int) -> bool:
        """
        Handle a detected connection failure.

        Args:
            current_connection: Current connection info dict with 'file' and 'mode' keys
            session_id: Session ID this failure belongs to (for validation)

        Returns:
            True if reconnection succeeded, False otherwise
        """
        # CHECKPOINT 1: Validate session before starting
        if not self._validate_session(session_id, "start"):
            return False

        logger.warning("[AutoReconnectService] Handling passive failure")
        if not self._emit_safe("failure_detected", session_id):
            return False

        # CHECKPOINT 2: Check internet availability
        if not self._validate_session(session_id, "internet_check"):
            return False

        if not self._network_validator.check_internet_connection():
            logger.warning("[AutoReconnectService] Internet is offline")
            self._emit_safe("reconnect_failed", session_id, {"reason": "no_internet"})
            return False

        # CHECKPOINT 3: Stabilization buffer (interruptible)
        logger.info(f"[AutoReconnectService] Waiting {self.STABILIZATION_BUFFER}s for stabilization...")

        # Use Event.wait() for interruptible sleep
        if self._cancel_event.wait(timeout=self.STABILIZATION_BUFFER):
            # Event was set = cancelled
            logger.info("[AutoReconnectService] Cancelled during stabilization wait")
            return False

        # CHECKPOINT 4: Validate session after wake
        if not self._validate_session(session_id, "post_stabilization"):
            return False

        # CHECKPOINT 5: Check if Xray recovered
        if current_connection:
            file_path = current_connection.get("file")
            if file_path and file_path != "Adopted Connection":
                if not self._validate_session(session_id, "recovery_check"):
                    return False
                if self._check_xray_recovered(file_path):
                    logger.info("[AutoReconnectService] Xray recovered, connection is healthy - no reconnect needed")
                    # Connection is already working - no event needed
                    # UI stays on current "connected" state
                    return True

        # CHECKPOINT 6: Attempt reconnect
        return self._attempt_reconnect(current_connection, session_id)

    def _validate_session(self, session_id: int, checkpoint: str) -> bool:
        """
        Validate that session is still active.

        Args:
            session_id: Session to validate
            checkpoint: Name of checkpoint for logging

        Returns:
            True if session is valid, False if cancelled/stale
        """
        with self._lock:
            if self._cancelled:
                logger.debug(f"[AutoReconnectService] Cancelled at {checkpoint}")
                return False
            if session_id != self._session_id:
                logger.debug(
                    f"[AutoReconnectService] Stale session at {checkpoint} "
                    f"(got {session_id}, current {self._session_id})"
                )
                return False
            return True

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

    def _attempt_reconnect(self, current_connection: Optional[dict], session_id: int) -> bool:
        """Attempt to reconnect using stored connection info."""
        # CHECKPOINT: Validate before reconnect
        if not self._validate_session(session_id, "pre_reconnect"):
            return False

        if not current_connection:
            logger.warning("[AutoReconnectService] No connection info available")
            self._emit_safe("reconnect_failed", session_id, {"reason": "no_connection"})
            return False

        file_path = current_connection.get("file")
        mode = current_connection.get("mode")

        if not file_path or not mode or file_path == "Adopted Connection":
            logger.warning("[AutoReconnectService] Invalid connection info")
            self._emit_safe("reconnect_failed", session_id, {"reason": "invalid_connection"})
            return False

        logger.info("[AutoReconnectService] Attempting reconnect...")
        if not self._emit_safe("reconnecting", session_id):
            return False

        # CHECKPOINT: Validate before actual connect call
        if not self._validate_session(session_id, "connect_call"):
            return False

        success = self._connect_fn(file_path, mode)

        # CHECKPOINT: Validate before emitting result
        if not self._validate_session(session_id, "post_connect"):
            return False

        # Note: connect() creates a NEW session and emits "connected" event automatically
        # The "reconnecting" → "connected" transition happens via that event
        if success:
            logger.info("[AutoReconnectService] Reconnect successful")
            # Don't emit "reconnected" - it would use stale session_id and get dropped
        else:
            logger.error("[AutoReconnectService] Reconnect failed")
            self._emit_safe("reconnect_failed", session_id, {"reason": "connect_failed"})

        return success

    def _emit_safe(self, event_type: str, session_id: int, data: dict = None) -> bool:
        """
        Emit an event only if session is still valid.

        Returns:
            True if event was emitted, False if session invalid
        """
        if not self._validate_session(session_id, f"emit_{event_type}"):
            return False

        if self._event_emitter:
            try:
                self._event_emitter(event_type, data or {})
            except Exception as e:
                logger.error(f"[AutoReconnectService] Error emitting event: {e}")
        return True
