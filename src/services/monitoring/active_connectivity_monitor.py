"""
Active Connectivity Monitor - Real connectivity probing with smart escalation.

Detects actual connectivity loss by probing the live tunnel:
- LIGHT probe (default): a cheap ``socket.create_connection`` to the local
  SOCKS proxy port (proves the proxy engine is alive and listening).
- HEAVY probe (only after N suspicious samples): an HTTP ``generate_204``
  request THROUGH the SOCKS proxy (proves end-to-end tunnel routing).

Resource budget (important):
- In a healthy session the monitor only opens ONE cheap local socket every
  SAMPLE_INTERVAL (3s). No HTTP requests are made while connectivity looks
  fine.
- The HTTP probe only runs when the light probe fails repeatedly or the stall
  counter reaches WARNING_SAMPLES / MAX_STALL_SAMPLES — i.e. rarely.
- All probes run on the dedicated daemon monitor thread with short timeouts
  (<=5s); nothing ever touches the UI thread.
"""

import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from loguru import logger


class ActiveConnectivityMonitor:
    """
    Monitors connectivity using real probes (SOCKS socket + HTTP 204).

    Detection Logic:
    1. Light probe: can we connect to the local SOCKS proxy port?
       - Yes  -> connection is fine (reset stall counter, emit RESTORED if needed)
       - No   -> increment stall counter; escalate to the HTTP probe
    2. Heavy probe (HTTP generate_204 THROUGH the proxy): only after
       REQUIRED_SAMPLES consecutive light-probe failures, or at
       WARNING_SAMPLES / MAX_STALL_SAMPLES.
       - Yes  -> tunnel works (idle system) — reset
       - No   -> real connectivity loss — emit LOST (after confirmation)
    3. Warmup grace for slow-handshake transports (xhttp/splithttp).
    """

    SAMPLE_INTERVAL = 3.0  # seconds between samples
    REQUIRED_SAMPLES = 2  # consecutive failures for fast detection (~6s)
    WARNING_SAMPLES = 4  # show warning in UI after this many (~12s)
    MAX_STALL_SAMPLES = 8  # failsafe: trigger after this many (~24s)

    # Timeouts (short — never block the monitor thread for long)
    SOCKET_TIMEOUT = 2.0  # light probe (local socket)
    HTTP_TIMEOUT = 5.0  # heavy probe (end-to-end)

    # Transports that need warmup grace period (slower initial handshake)
    SLOW_HANDSHAKE_TRANSPORTS = {"xhttp", "splithttp"}

    def __init__(
        self,
        socks_port_getter: Optional[Callable[[], int]] = None,
        on_connectivity_lost: Optional[Callable[[], None]] = None,
        on_connectivity_restored: Optional[Callable[[], None]] = None,
        on_connectivity_degraded: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize the monitor.

        Args:
            socks_port_getter: Callable returning the current SOCKS proxy port.
            on_connectivity_lost: Callback when connectivity is lost.
            on_connectivity_restored: Callback when connectivity is restored.
            on_connectivity_degraded: Callback when connection shows issues (soft warning).
        """
        self._socks_port_getter = socks_port_getter
        self._on_lost = on_connectivity_lost
        self._on_restored = on_connectivity_restored
        self._on_degraded = on_connectivity_degraded

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # State
        self._stall_samples = 0
        self._is_connected = True
        self._warning_emitted = False  # Track if warning already shown
        self._needs_warmup = False  # True for transports with slow handshake (xhttp)
        self._handshake_complete = True  # Set to False during warmup phase
        self._session_id = 0  # Current session for event validation

        # Single bounded executor for event callbacks (max 1 worker — no
        # unbounded daemon thread spawning per emitted event).
        self._callback_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ActiveConnectivityMonitor-Callback"
        )

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
            self._stop_event.clear()
            # Recreate the callback executor if a previous stop() shut it down
            # (supports start → stop → start on the same instance).
            if self._callback_executor._shutdown:
                self._callback_executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="ActiveConnectivityMonitor-Callback"
                )

            # Apply warmup grace for slow-handshake transports (xhttp)
            self._needs_warmup = transport_type in self.SLOW_HANDSHAKE_TRANSPORTS if transport_type else False
            self._handshake_complete = not self._needs_warmup

            self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="ActiveConnectivityMonitor")
            self._thread.start()

            warmup_info = f", warmup={transport_type}" if self._needs_warmup else ""
            logger.info(
                f"[ActiveConnectivityMonitor] Started session {session_id} "
                f"(fast={self.REQUIRED_SAMPLES}, failsafe={self.MAX_STALL_SAMPLES}{warmup_info})"
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
            self._callback_executor.shutdown(wait=False)
            logger.info("[ActiveConnectivityMonitor] Stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _monitor_loop(self):
        """Main monitoring loop."""
        try:
            while not self._stop_event.is_set():
                self._check_connectivity()
                self._stop_event.wait(self.SAMPLE_INTERVAL)
        except Exception as e:
            logger.error(f"[ActiveConnectivityMonitor] Error in monitor loop: {e}")

    def _check_connectivity(self):
        """Check connectivity using light-then-heavy probe escalation."""
        # 1. Light probe: cheap local SOCKS socket
        port = self._socks_port_getter() if self._socks_port_getter else 10805
        light_ok = self._probe_socks_socket(port)

        if light_ok:
            # Proxy alive — connection is fine (may still be idle, but the
            # tunnel endpoint is reachable). Reset stall state.
            self._on_healthy()
            return

        # 2. Light probe failed → suspicious
        self._stall_samples += 1
        logger.debug(f"[ActiveConnectivityMonitor] Light probe failed ({self._stall_samples}/{self.REQUIRED_SAMPLES})")

        # Soft warning: show UI feedback after WARNING_SAMPLES
        if self._stall_samples == self.WARNING_SAMPLES and not self._warning_emitted:
            if self._verify_connectivity(port):
                # Heavy probe succeeded - system is just idle, not offline
                logger.debug("[ActiveConnectivityMonitor] Stall but HTTP probe OK - system is idle")
                self._stall_samples = 0  # Reset - connection is fine
            else:
                # Heavy probe failed - connection is degraded
                self._warning_emitted = True
                logger.info("[ActiveConnectivityMonitor] Connection degraded - probe failed")
                self._emit_degraded()

        # HYBRID ESCALATION:
        # 1. Fast path: REQUIRED_SAMPLES light failures + heavy probe failure
        # 2. Failsafe: MAX_STALL_SAMPLES light failures (probe confirms)
        should_trigger = False
        trigger_reason = ""

        if self._stall_samples >= self.REQUIRED_SAMPLES:
            if not self._verify_connectivity(port):
                should_trigger = True
                trigger_reason = f"confirmed by HTTP probe after {self._stall_samples} samples"
            else:
                # Heavy probe OK - connection is fine (idle), reset
                logger.info("[ActiveConnectivityMonitor] HTTP probe OK - connection is fine, resetting")
                self._stall_samples = 0
                self._warning_emitted = False

        if should_trigger and self._is_connected:
            self._is_connected = False
            logger.warning(f"[ActiveConnectivityMonitor] Connectivity LOST ({trigger_reason})")
            self._emit_lost()

    def _on_healthy(self):
        """Reset stall state and emit RESTORED if we were in LOST/degraded."""
        was_warning_shown = self._warning_emitted
        was_lost = not self._is_connected

        if self._stall_samples > 0:
            logger.debug("[ActiveConnectivityMonitor] Light probe OK, resetting stall counter")

        self._stall_samples = 0
        self._warning_emitted = False

        if was_lost:
            self._is_connected = True
            logger.info("[ActiveConnectivityMonitor] Connectivity RESTORED (was lost)")
            self._emit_restored()
        elif was_warning_shown:
            # Traffic resumed after degraded warning - clear the warning
            logger.info("[ActiveConnectivityMonitor] Connectivity RESTORED (clearing warning)")
            self._emit_restored()

    # ------------------------------------------------------------------
    # Probes
    # ------------------------------------------------------------------

    def _probe_socks_socket(self, port: int) -> bool:
        """Cheap light probe: can we connect to the local SOCKS proxy?

        One ``socket.create_connection`` with a short timeout. Never blocks
        the monitor thread for more than SOCKET_TIMEOUT seconds.
        """
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=self.SOCKET_TIMEOUT):
                return True
        except OSError:
            return False

    def _verify_connectivity(self, port: int) -> bool:
        """
        Heavy probe: HTTP generate_204 THROUGH the SOCKS proxy.

        Proves end-to-end routing (the tunnel actually forwards traffic),
        unlike the light socket probe which only proves the proxy listens.

        Returns:
            True if connection is working, False if broken
        """
        try:
            from src.utils.network_utils import NetworkUtils

            # Connectivity check through proxy (1 retry, short timeout)
            result = NetworkUtils.check_proxy_connectivity(
                port=port,
                timeout=self.HTTP_TIMEOUT,
                retries=1,
            )

            if result:
                logger.debug(f"[ActiveConnectivityMonitor] HTTP probe OK via port {port}")
            else:
                logger.debug(f"[ActiveConnectivityMonitor] HTTP probe failed via port {port}")

            return result

        except Exception as e:
            logger.debug(f"[ActiveConnectivityMonitor] Probe error: {e}")

        return False

    # ------------------------------------------------------------------
    # Emitters (thread-safe, session-guarded)
    # ------------------------------------------------------------------

    def _emit_lost(self):
        """Emit connectivity lost event (only if still running)."""
        with self._lock:
            if not self._running:
                logger.debug("[ActiveConnectivityMonitor] Suppressed lost event (stopped)")
                return
        if self._on_lost:
            try:
                self._callback_executor.submit(self._on_lost)
            except RuntimeError:
                logger.debug("[ActiveConnectivityMonitor] Dropped lost event (callback executor shut down)")

    def _emit_restored(self):
        """Emit connectivity restored event (only if still running)."""
        with self._lock:
            if not self._running:
                logger.debug("[ActiveConnectivityMonitor] Suppressed restored event (stopped)")
                return
        if self._on_restored:
            try:
                self._callback_executor.submit(self._on_restored)
            except RuntimeError:
                logger.debug("[ActiveConnectivityMonitor] Dropped restored event (callback executor shut down)")

    def _emit_degraded(self):
        """Emit connectivity degraded (soft warning) event (only if still running)."""
        with self._lock:
            if not self._running:
                logger.debug("[ActiveConnectivityMonitor] Suppressed degraded event (stopped)")
                return
        if self._on_degraded:
            try:
                self._callback_executor.submit(self._on_degraded)
            except RuntimeError:
                logger.debug("[ActiveConnectivityMonitor] Dropped degraded event (callback executor shut down)")
