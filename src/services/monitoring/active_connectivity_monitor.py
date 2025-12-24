"""Active Connectivity Monitor - Metrics-based connectivity detection with smart stall detection."""

import threading
from typing import Callable, Optional

from loguru import logger

from src.services.singbox_metrics_provider import MetricsSnapshot, SingBoxMetricsProvider


class ActiveConnectivityMonitor:
    """
    Monitors connectivity using sing-box metrics with smart stall detection.

    Detection Logic (ALL must be true):
    1. sing-box process is running
    2. Traffic delta < MIN_TRAFFIC_THRESHOLD for ≥ N samples (~6-9 seconds)

    Key Insight: "Traffic is not truly flowing — it is only retry noise."
    Small deltas (< 500 bytes) are TCP retries, not real traffic.

    Xray confirmation is optional/confirmatory, not blocking.
    """

    SAMPLE_INTERVAL = 3.0  # seconds between samples
    REQUIRED_SAMPLES = 2  # consecutive samples for fast detection (~6s)
    WARNING_SAMPLES = 4  # show warning in UI after this many stalls (~12s)
    MAX_STALL_SAMPLES = 8  # failsafe: trigger after this many (~24s)
    MIN_TRAFFIC_THRESHOLD = 200  # bytes - below this is "stalled" (HTTP probe verifies actual connectivity)
    MIN_HANDSHAKE_BYTES = 1000  # bytes - meaningful traffic indicating handshake complete

    # Transports that need warmup grace period (slower initial handshake)
    SLOW_HANDSHAKE_TRANSPORTS = {"xhttp", "splithttp"}

    def __init__(
        self,
        metrics_provider: SingBoxMetricsProvider,
        on_connectivity_lost: Optional[Callable[[], None]] = None,
        on_connectivity_restored: Optional[Callable[[], None]] = None,
        on_connectivity_degraded: Optional[Callable[[], None]] = None,
        xray_error_checker: Optional[Callable[[], bool]] = None,
    ):
        """
        Initialize the monitor.

        Args:
            metrics_provider: Provider implementing SingBoxMetricsProvider protocol
            on_connectivity_lost: Callback when connectivity is lost
            on_connectivity_restored: Callback when connectivity is restored
            on_connectivity_degraded: Callback when connection shows issues (soft warning)
            xray_error_checker: Optional callback for Xray error confirmation
        """
        self._provider = metrics_provider
        self._on_lost = on_connectivity_lost
        self._on_restored = on_connectivity_restored
        self._on_degraded = on_connectivity_degraded
        self._xray_error_checker = xray_error_checker

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # State
        self._last_snapshot: Optional[MetricsSnapshot] = None
        self._stall_samples = 0
        self._is_connected = True
        self._warning_emitted = False  # Track if warning already shown
        self._needs_warmup = False  # True for transports with slow handshake (xhttp)
        self._handshake_complete = True  # Set to False during warmup phase
        self._session_id = 0  # Current session for event validation

    def start(self, transport_type: str = None, session_id: int = 0):
        """
        Start the monitoring thread.

        Args:
            transport_type: Optional transport type (e.g., 'xhttp', 'ws').
                           Used to apply warmup grace for slow-handshake transports.
            session_id: Connection session ID for event validation.
        """
        with self._lock:
            if self._running:
                return

            self._running = True
            self._session_id = session_id
            self._stall_samples = 0
            self._is_connected = True
            self._warning_emitted = False
            self._last_snapshot = None  # Reset snapshot on new session
            self._stop_event.clear()

            # Apply warmup grace for slow-handshake transports (xhttp)
            self._needs_warmup = transport_type in self.SLOW_HANDSHAKE_TRANSPORTS if transport_type else False
            self._handshake_complete = not self._needs_warmup

            self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="ActiveConnectivityMonitor")
            self._thread.start()

            warmup_info = f", warmup={transport_type}" if self._needs_warmup else ""
            logger.info(
                f"[ActiveConnectivityMonitor] Started session {session_id} "
                f"(threshold={self.MIN_TRAFFIC_THRESHOLD}b, "
                f"fast={self.REQUIRED_SAMPLES}, failsafe={self.MAX_STALL_SAMPLES}{warmup_info})"
            )

    def stop(self):
        """Stop the monitoring thread immediately. Prevents any further event emissions."""
        with self._lock:
            if not self._running:
                return

            self._running = False
            self._session_id = 0  # Invalidate session to prevent late events
            self._stop_event.set()

            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)

            self._thread = None
            logger.info("[ActiveConnectivityMonitor] Stopped")

    def is_running(self) -> bool:
        """Check if monitor is currently running."""
        with self._lock:
            return self._running

    def _monitor_loop(self):
        """Main monitoring loop."""
        try:
            while not self._stop_event.is_set():
                self._check_connectivity()
                self._stop_event.wait(self.SAMPLE_INTERVAL)
        except Exception as e:
            logger.error(f"[ActiveConnectivityMonitor] Error in monitor loop: {e}")

    def _check_connectivity(self):
        """Check connectivity using hybrid escalation."""
        snapshot = self._provider.fetch_snapshot()

        if snapshot is None:
            logger.warning("[ActiveConnectivityMonitor] Failed to fetch snapshot")
            return

        # Handle warmup phase for slow-handshake transports (xhttp)
        if not self._handshake_complete:
            if self._last_snapshot is not None:
                # Check if we've seen meaningful traffic (handshake complete)
                delta = (snapshot.uplink_bytes + snapshot.downlink_bytes) - (
                    self._last_snapshot.uplink_bytes + self._last_snapshot.downlink_bytes
                )
                if delta >= self.MIN_HANDSHAKE_BYTES:
                    self._handshake_complete = True
                    logger.info(
                        f"[ActiveConnectivityMonitor] Handshake complete (delta={delta}b), "
                        "activating stall detection"
                    )
                else:
                    logger.debug(
                        f"[ActiveConnectivityMonitor] Warmup phase: delta={delta}b "
                        f"(waiting for {self.MIN_HANDSHAKE_BYTES}b)"
                    )
            self._last_snapshot = snapshot
            return

        # Evaluate stall condition
        is_stalled = self._evaluate_stall_condition(snapshot)

        if is_stalled:
            self._stall_samples += 1

            # Check Xray confirmation
            has_xray_errors = False
            if self._xray_error_checker:
                has_xray_errors = self._xray_error_checker()

            logger.debug(
                f"[ActiveConnectivityMonitor] Stall detected "
                f"({self._stall_samples}/{self.REQUIRED_SAMPLES}) "
                f"[Xray: {'confirmed' if has_xray_errors else 'waiting'}]"
            )

            # Soft warning: show UI feedback after WARNING_SAMPLES
            # BUT first verify with a quick probe (idle vs offline)
            if self._stall_samples == self.WARNING_SAMPLES and not self._warning_emitted:
                if self._verify_connectivity():
                    # Probe succeeded - system is just idle, not offline
                    logger.debug("[ActiveConnectivityMonitor] Stall but probe OK - system is idle")
                    self._stall_samples = 0  # Reset - connection is fine
                else:
                    # Probe failed - connection is degraded
                    self._warning_emitted = True
                    logger.info("[ActiveConnectivityMonitor] Connection degraded - probe failed")
                    self._emit_degraded()

            # HYBRID ESCALATION:
            # 1. Fast path: stall + Xray confirmation → immediate trigger
            # 2. Failsafe: extended stall without traffic → trigger anyway (with probe)
            should_trigger = False
            trigger_reason = ""

            if self._stall_samples >= self.REQUIRED_SAMPLES and has_xray_errors:
                should_trigger = True
                trigger_reason = "confirmed by Xray"
            elif self._stall_samples >= self.MAX_STALL_SAMPLES:
                # Before failsafe trigger, do a final probe
                if not self._verify_connectivity():
                    should_trigger = True
                    trigger_reason = f"failsafe after {self.MAX_STALL_SAMPLES} samples (probe failed)"
                else:
                    # Probe succeeded - reset and continue
                    logger.info("[ActiveConnectivityMonitor] Failsafe probe OK - connection is fine, resetting")
                    self._stall_samples = 0
                    self._warning_emitted = False

            if should_trigger and self._is_connected:
                self._is_connected = False
                logger.warning(f"[ActiveConnectivityMonitor] Connectivity LOST ({trigger_reason})")
                self._emit_lost()
        else:
            # Traffic is flowing - clear stall state
            was_warning_shown = self._warning_emitted

            if self._stall_samples > 0:
                logger.debug("[ActiveConnectivityMonitor] Traffic resumed, resetting stall counter")

            self._stall_samples = 0
            self._warning_emitted = False

            # CRITICAL: Emit RESTORED if either:
            # 1. We were in LOST state (_is_connected = False)
            # 2. We had shown a warning (degraded) and now traffic resumed
            if not self._is_connected:
                self._is_connected = True
                logger.info("[ActiveConnectivityMonitor] Connectivity RESTORED (was lost)")
                self._emit_restored()
            elif was_warning_shown:
                # Traffic resumed after degraded warning - clear the warning
                logger.info("[ActiveConnectivityMonitor] Connectivity RESTORED (clearing warning)")
                self._emit_restored()

        self._last_snapshot = snapshot

    def _evaluate_stall_condition(self, snapshot: MetricsSnapshot) -> bool:
        """
        Evaluate if traffic is stalled using MIN_TRAFFIC_THRESHOLD.

        Traffic is considered STALLED if:
        - Process is alive
        - Δ(uplink + downlink) < MIN_TRAFFIC_THRESHOLD

        This ignores TCP retries, buffer flushes, and noise.
        """
        # Process must be running
        if not snapshot.process_alive:
            return False

        # First sample - can't compare
        if self._last_snapshot is None:
            return False

        # Calculate traffic delta
        last_traffic = self._last_snapshot.uplink_bytes + self._last_snapshot.downlink_bytes
        current_traffic = snapshot.uplink_bytes + snapshot.downlink_bytes
        delta = current_traffic - last_traffic

        # Stalled if delta is below threshold (retry noise level)
        is_stalled = delta < self.MIN_TRAFFIC_THRESHOLD

        if is_stalled:
            logger.debug(
                f"[ActiveConnectivityMonitor] Traffic delta: {delta}b " f"(< {self.MIN_TRAFFIC_THRESHOLD}b threshold)"
            )

        return is_stalled

    def _verify_connectivity(self) -> bool:
        """
        Quick HTTP probe to verify actual connectivity.

        Used to distinguish between:
        - Idle system (no traffic, but connection works) → return True
        - Offline (connection is actually broken) → return False

        Returns:
            True if connection is working, False if broken
        """
        try:
            from src.utils.network_utils import NetworkUtils

            # Quick connectivity check through proxy (1 retry, 2s timeout)
            result = NetworkUtils.check_proxy_connectivity(
                port=10805,
                timeout=2,
                retries=1,
            )

            if result:
                logger.debug("[ActiveConnectivityMonitor] Probe OK")
            else:
                logger.debug("[ActiveConnectivityMonitor] Probe failed")

            return result

        except Exception as e:
            logger.debug(f"[ActiveConnectivityMonitor] Probe error: {e}")

        return False

    def _emit_lost(self):
        """Emit connectivity lost event (only if still running)."""
        with self._lock:
            if not self._running:
                logger.debug("[ActiveConnectivityMonitor] Suppressed lost event (stopped)")
                return
        if self._on_lost:
            try:
                threading.Thread(
                    target=self._on_lost, daemon=True, name="ActiveConnectivityMonitor-LostCallback"
                ).start()
            except Exception as e:
                logger.error(f"[ActiveConnectivityMonitor] Error in lost callback: {e}")

    def _emit_restored(self):
        """Emit connectivity restored event (only if still running)."""
        with self._lock:
            if not self._running:
                logger.debug("[ActiveConnectivityMonitor] Suppressed restored event (stopped)")
                return
        if self._on_restored:
            try:
                threading.Thread(
                    target=self._on_restored, daemon=True, name="ActiveConnectivityMonitor-RestoredCallback"
                ).start()
            except Exception as e:
                logger.error(f"[ActiveConnectivityMonitor] Error in restored callback: {e}")

    def _emit_degraded(self):
        """Emit connectivity degraded (soft warning) event (only if still running)."""
        with self._lock:
            if not self._running:
                logger.debug("[ActiveConnectivityMonitor] Suppressed degraded event (stopped)")
                return
        if self._on_degraded:
            try:
                threading.Thread(
                    target=self._on_degraded, daemon=True, name="ActiveConnectivityMonitor-DegradedCallback"
                ).start()
            except Exception as e:
                logger.error(f"[ActiveConnectivityMonitor] Error in degraded callback: {e}")
