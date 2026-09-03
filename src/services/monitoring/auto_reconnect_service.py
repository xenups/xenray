"""Auto-Reconnect Service - Handles passive failure recovery with session scoping."""

import random
import threading
import time
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

    Reconnect semantics:
    - A reconnect is a FRESH connection attempt that owns a NEW session
      (``ConnectionManager._reconnect_internal`` bumps ``_session_id`` and
      tears down the previous engine).
    - The ``reconnecting`` event is emitted BEFORE the ``connect_fn`` call
      (against the still-valid OLD session) so the UI reacts immediately.
    - After a SUCCESSFUL reconnect the new session emits ``connected``; we do
      NOT emit ``reconnected`` against the (now stale) old session.
    - After a FAILED reconnect we emit ``reconnect_failed`` with a reason
      against the ORIGINAL session (still valid while it exists).

    State Guarantees:
    - Disconnect is terminal: no automatic restart possible
    - Cancellation is checked at every checkpoint
    - Events are only emitted if session is still valid
    """

    STABILIZATION_BUFFER = 2.0  # seconds to wait before reconnect
    BASE_COOLDOWN_SECONDS = 2.0  # T_base = 2s
    MAX_COOLDOWN_SECONDS = 60.0  # T_max = 60s
    MAX_CONSECUTIVE_ATTEMPTS = 5  # Cap at 5 attempts before Pausing
    WATCHDOG_INTERVAL_SECONDS = 30.0  # Watchdog re-check in Paused state (30s-45s tuned)

    def __init__(
        self,
        network_validator,
        config_loader: Callable[[str], tuple],
        connection_tester,
        connect_fn: Callable[[str, str, Optional[dict]], bool],
        event_emitter: Callable[[str, dict], None],
        internet_check: Optional[Callable[[Optional[dict]], bool]] = None,
    ):
        """
        Initialize AutoReconnectService.

        Args:
            network_validator: Service to check internet connectivity
            config_loader: Function to load config from file path -> (config, error)
            connection_tester: ConnectionTester class/instance for health checks
            connect_fn: Function to establish connection
                (file_path, mode, connection_info) -> success
            event_emitter: Function to emit events (event_type, data)
            internet_check: Optional mode-aware internet availability check that
                receives the current connection dict. Falls back to
                network_validator.check_internet_connection() when omitted.
        """
        self._network_validator = network_validator
        self._config_loader = config_loader
        self._connection_tester = connection_tester
        self._connect_fn = connect_fn
        self._event_emitter = event_emitter
        self._internet_check = internet_check
        self._lock = threading.RLock()

        # Session-scoped cancellation
        self._session_id = 0  # Incremented on each new connection
        self._cancel_event = threading.Event()
        self._cancelled = False

        # Reconnect backoff state
        self._consecutive_failures = 0
        self._last_attempt_time = 0.0
        self._is_reconnecting = False

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
            self._consecutive_failures = 0
            self._last_attempt_time = 0.0
            self._is_reconnecting = False
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
            self._is_reconnecting = False
            logger.info(f"[AutoReconnectService] Session {self._session_id} cancelled (hard override)")

    def is_cancelled(self) -> bool:
        """Check if current session is cancelled."""
        with self._lock:
            return self._cancelled

    def _backoff_seconds(self) -> float:
        """Exponential backoff: min(T_max, T_base * 2^(attempt - 1)) ± 20% jitter.

        Attempt 0 is executed immediately (0s delay, not part of backoff wait).
        Subsequent retries (attempts 1..5) scale as:
        Attempt 1: 2s ± 20% (1.6s - 2.4s)
        Attempt 2: 4s ± 20% (3.2s - 4.8s)
        Attempt 3: 8s ± 20% (6.4s - 9.6s)
        Attempt 4: 16s ± 20% (12.8s - 19.2s)
        Attempt 5: 32s ± 20% (25.6s - 38.4s)
        """
        if self._consecutive_failures <= 0:
            return 0.0
        exponent = max(self._consecutive_failures - 1, 0)
        base = min(
            self.BASE_COOLDOWN_SECONDS * (2**exponent),
            self.MAX_COOLDOWN_SECONDS,
        )
        jitter = random.uniform(-0.20, 0.20)
        return max(1.0, base * (1.0 + jitter))

    def reset_backoff(self, reason: str = "network_event"):
        """Reset consecutive failure counter on external network restore event (e.g. link flap)."""
        with self._lock:
            logger.info(f"[AutoReconnectService] Resetting backoff counter (reason: {reason})")
            self._consecutive_failures = 0

    def _start_watchdog_timer(
        self,
        current_connection: Optional[dict],
        session_id: int,
        interval: Optional[float] = None,
    ):
        """Watchdog timer in paused state to re-check physical link with loop-breaker backoff.

        If physical gateway is UP but server is unreachable, prevents infinite retry loops
        by executing a single-shot probe and doubling the interval up to 300s (5m).
        """
        watchdog_interval = interval or self.WATCHDOG_INTERVAL_SECONDS

        def _watchdog_worker():
            logger.info(f"[AutoReconnectService] Watchdog timer started ({watchdog_interval:.1f}s)")
            if self._cancel_event.wait(timeout=watchdog_interval):
                return
            with self._lock:
                if self._cancelled or session_id != self._session_id:
                    return
                # Check if physical link is alive
                internet_ok = (
                    self._internet_check(current_connection)
                    if self._internet_check
                    else self._network_validator.check_internet_connection()
                )
                if internet_ok:
                    logger.info(
                        "[AutoReconnectService] Watchdog detected physical gateway UP. "
                        "Executing single-shot recovery probe..."
                    )
                    # Allow 1 attempt (set count to 4 so failure immediately repauses)
                    self._consecutive_failures = self.MAX_CONSECUTIVE_ATTEMPTS - 1

                    def _reconnect_and_check():
                        success = self.handle_failure(current_connection, session_id)
                        if not success:
                            # Server unreachable despite physical link -> backoff watchdog up to 5m
                            next_interval = min(watchdog_interval * 2.0, 300.0)
                            logger.warning(
                                f"[AutoReconnectService] Server unreachable despite physical link. "
                                f"Backing off watchdog to {next_interval:.1f}s"
                            )
                            self._emit_safe(
                                "reconnect_paused",
                                session_id,
                                {
                                    "reason": "server_unreachable_gateway_ok",
                                    "watchdog_interval": next_interval,
                                },
                            )
                            self._start_watchdog_timer(current_connection, session_id, interval=next_interval)

                    threading.Thread(
                        target=_reconnect_and_check,
                        daemon=True,
                        name="AutoReconnectWatchdogTrigger",
                    ).start()
                else:
                    self._start_watchdog_timer(current_connection, session_id, interval=self.WATCHDOG_INTERVAL_SECONDS)

        threading.Thread(target=_watchdog_worker, daemon=True, name="AutoReconnectWatchdog").start()

    def _schedule_retry(self, current_connection: Optional[dict], session_id: int):
        """Schedule next reconnect attempt on a background daemon thread."""
        with self._lock:
            if self._consecutive_failures >= self.MAX_CONSECUTIVE_ATTEMPTS:
                return
            wait = self._backoff_seconds()

        def _worker():
            logger.info(f"[AutoReconnectService] Scheduling next attempt in {wait:.1f}s")
            if self._cancel_event.wait(timeout=wait):
                return
            if self._validate_session(session_id, "retry_worker"):
                self.handle_failure(current_connection, session_id)

        threading.Thread(target=_worker, daemon=True, name="AutoReconnectRetry").start()

    def _respect_backoff(self, session_id: int) -> bool:
        """If a reconnect attempt happened recently, wait out the backoff
        (interruptible by cancel) before the next attempt.

        Returns True if we may proceed, False if cancelled during the wait.
        """
        with self._lock:
            elapsed = time.time() - self._last_attempt_time
            wait = self._backoff_seconds() - elapsed
            if self._last_attempt_time == 0.0 or wait <= 0:
                return True

        logger.info(f"[AutoReconnectService] Backing off {wait:.1f}s before next attempt")
        if self._cancel_event.wait(timeout=wait):
            logger.info("[AutoReconnectService] Cancelled during backoff wait")
            return False

        # Re-validate session after the wait
        return self._validate_session(session_id, "post_backoff")

    def handle_failure(self, current_connection: Optional[dict], session_id: int) -> bool:
        """
        Handle a detected connection failure.

        Args:
            current_connection: Current connection info dict with 'file' and 'mode' keys
            session_id: Session ID this failure belongs to (for validation)

        Returns:
            True if reconnection succeeded, False otherwise
        """
        with self._lock:
            if self._is_reconnecting:
                logger.info(
                    f"[AutoReconnectService] Reconnect attempt already in-flight for session {session_id}. "
                    "Skipping concurrent handle_failure invocation."
                )
                return False
            self._is_reconnecting = True

        try:
            return self._handle_failure_inner(current_connection, session_id)
        finally:
            with self._lock:
                self._is_reconnecting = False

    def _handle_failure_inner(self, current_connection: Optional[dict], session_id: int) -> bool:
        # CHECKPOINT 0: Max consecutive attempts ceiling
        with self._lock:
            if self._consecutive_failures >= self.MAX_CONSECUTIVE_ATTEMPTS:
                logger.warning(
                    f"[AutoReconnectService] Max attempts ({self.MAX_CONSECUTIVE_ATTEMPTS}) reached. "
                    "Pausing auto-reconnect — Manual Action Required."
                )
                self._emit_safe(
                    "reconnect_paused",
                    session_id,
                    {"reason": "max_attempts_reached", "attempts": self._consecutive_failures},
                )
                self._start_watchdog_timer(current_connection, session_id)
                return False

        # CHECKPOINT 1: Validate session before starting
        if not self._validate_session(session_id, "start"):
            return False

        # CHECKPOINT 1.5: Respect backoff (no reconnect storms)
        if not self._respect_backoff(session_id):
            return False

        logger.warning("[AutoReconnectService] Handling passive failure")
        if not self._emit_safe("failure_detected", session_id):
            return False

        # CHECKPOINT 2: Check internet availability
        if not self._validate_session(session_id, "internet_check"):
            return False

        if self._internet_check:
            internet_ok = self._internet_check(current_connection)
        else:
            internet_ok = self._network_validator.check_internet_connection()

        if not internet_ok:
            logger.warning("[AutoReconnectService] Internet is offline")
            with self._lock:
                self._consecutive_failures += 1
            self._emit_safe("reconnect_failed", session_id, {"reason": "no_internet"})
            self._schedule_retry(current_connection, session_id)
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

        # CHECKPOINT 5: Check if the core recovered
        if current_connection:
            file_path = current_connection.get("file")
            if file_path and file_path != "Adopted Connection":
                if not self._validate_session(session_id, "recovery_check"):
                    return False
                if self._check_core_recovered(file_path):
                    logger.info("[AutoReconnectService] Core recovered, connection is healthy - no reconnect needed")
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

    def _check_core_recovered(self, file_path: str) -> bool:
        """Check if the core has self-recovered by testing connectivity."""
        try:
            config, _ = self._config_loader(file_path)
            if config:
                logger.debug("[AutoReconnectService] Testing if core recovered...")
                success, latency, _ = self._connection_tester.test_connection_sync(config)
                if success:
                    logger.info(f"[AutoReconnectService] Core recovered (latency: {latency})")
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

        # Record attempt time (for backoff) and emit "reconnecting" BEFORE the
        # connect call — the OLD session is still valid here, so the UI reacts
        # immediately. After connect() the session moves on.
        with self._lock:
            self._last_attempt_time = time.time()

        logger.info("[AutoReconnectService] Attempting reconnect...")
        if not self._emit_safe("reconnecting", session_id):
            return False

        # CHECKPOINT: Validate before actual connect call
        if not self._validate_session(session_id, "connect_call"):
            return False

        success = self._connect_fn(file_path, mode, current_connection)

        # NOTE: connect() creates a NEW session and emits "connected" event
        # automatically. The "reconnecting" → "connected" transition happens via
        # that event (ReconnectEventHandler listens for "connected").
        #
        # IMPORTANT (session semantics): after a successful reconnect the
        # session_id has MOVED ON (connect() bumped it). Emitting "reconnected"
        # against the OLD session_id here is impossible by design, so we only
        # report success/failure.
        if success:
            logger.info("[AutoReconnectService] Reconnect successful")
            with self._lock:
                self._consecutive_failures = 0
            # Don't emit "reconnected" - the new session owns the "connected"
            # event and emitting against the stale session_id would get dropped.
        else:
            logger.error("[AutoReconnectService] Reconnect failed")
            with self._lock:
                self._consecutive_failures += 1
            # A failed reconnect runs inside the SAME (still valid) session, so
            # the failure event is still emitted against it.
            self._emit_safe("reconnect_failed", session_id, {"reason": "connect_failed"})
            self._schedule_retry(current_connection, session_id)

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
