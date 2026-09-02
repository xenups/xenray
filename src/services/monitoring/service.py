"""
Connection Monitoring Service - Centralized monitoring facade.

Consolidates all connection monitoring (passive log, active stall detection,
auto-reconnect) into a single lifecycle-aware service.

Architecture:
- Monitors emit SIGNALS (facts) - no event semantics
- This service validates session/lifecycle and forwards signals
- ConnectionManager is the SINGLE EVENT AUTHORITY that:
  * Converts signals → user-visible events
  * Decides whether to start reconnect
  * Ignores late signals after disconnect
"""

import threading
from typing import Callable, Optional

from loguru import logger

from src.core.app_context import AppContext
from src.services.connection.connection_tester import ConnectionTester
from src.services.connection.network_validator import NetworkValidator

from .active_connectivity_monitor import ActiveConnectivityMonitor
from .auto_reconnect_service import AutoReconnectService
from .passive_log_monitor import PassiveLogMonitor
from .signals import MonitorSignal


class ConnectionMonitoringService:
    """
    Facade for all connection monitoring services.

    Signal-Based Architecture:
    - Monitors emit signals (facts), not events
    - This service validates session and forwards signals upward
    - ConnectionManager is the single event authority

    All monitors are created internally - just provide callbacks.
    """

    def __init__(
        self,
        app_context: AppContext,
        on_signal: Callable[[MonitorSignal, Optional[dict]], None],
        on_reconnect: Callable[[str, str, Optional[dict]], bool],
        on_reconnect_event: Callable[[str, dict], None],
    ):
        """
        Initialize the monitoring service with signal callback.

        Args:
            app_context: For checking auto-reconnect enabled setting
            on_signal: Single callback for ALL monitor signals (session-validated)
            on_reconnect: Called to attempt reconnection (file_path, mode, connection_info) -> success
            on_reconnect_event: Called by AutoReconnectService for reconnect-specific events
        """
        self._app_context = app_context
        self._on_signal = on_signal

        self._lock = threading.Lock()
        self._session_id = 0
        self._is_running = False

        # Create NetworkValidator for auto-reconnect service
        self._network_validator = NetworkValidator()

        # Create PassiveLogMonitor (log-based failure detection)
        # Emits PASSIVE_FAILURE signal (with source: xray|singbox)
        self._log_monitor = PassiveLogMonitor(
            on_failure_callback=lambda payload: self._emit_signal(MonitorSignal.PASSIVE_FAILURE, payload)
        )
        # FP guard: require repeated failure lines before alerting. One-off
        # dial errors to a single endpoint are noise; a real outage repeats.
        self._log_monitor.REQUIRED_FAILURE_LINES = 3

        # Create AutoReconnectService
        # Only emits reconnect-flow events, not monitor signals
        self._auto_reconnect = AutoReconnectService(
            network_validator=self._network_validator,
            config_loader=app_context.load_config,
            connection_tester=ConnectionTester,
            connect_fn=on_reconnect,
            event_emitter=on_reconnect_event,
            internet_check=self._mode_aware_internet_check,
        )

        # Create ActiveConnectivityMonitor (real probe-based, VPN mode)
        # Emits ACTIVE_LOST, ACTIVE_RESTORED, ACTIVE_DEGRADED signals
        self._active_monitor = ActiveConnectivityMonitor(
            socks_port_getter=app_context.settings.get_proxy_port,
            on_connectivity_lost=lambda: self._emit_signal(MonitorSignal.ACTIVE_LOST),
            on_connectivity_restored=lambda: self._emit_signal(MonitorSignal.ACTIVE_RESTORED),
            on_connectivity_degraded=lambda: self._emit_signal(MonitorSignal.ACTIVE_DEGRADED),
        )

    def _emit_signal(self, signal: MonitorSignal, payload: dict = None):
        """
        Validate session and forward signal + payload to ConnectionManager.

        All signals are validated here to prevent late emissions after disconnect.
        ConnectionManager then decides what event (if any) to emit.

        The payload (a plain fact container, e.g. ``{"source": "xray"}``) is
        forwarded verbatim — monitors own the facts, ConnectionManager owns
        the policy.
        """
        with self._lock:
            if not self._is_running:
                logger.debug(f"[MonitoringService] Signal {signal.name} ignored (not running)")
                return
            session_id = self._session_id

        logger.debug(f"[MonitoringService] Signal {signal.name} (session {session_id})")
        self._on_signal(signal, payload)

    def start(
        self,
        session_id: int,
        mode: str = "vpn",
        transport_type: Optional[str] = None,
    ) -> bool:
        """
        Start all monitoring services for a new connection.

        This is the SINGLE decision point for whether monitoring is enabled.
        All monitors are scoped to the provided session_id.

        Args:
            session_id: Unique connection session ID
            mode: Connection mode ("vpn" or "proxy")
            transport_type: Transport type for warmup handling (e.g., "xhttp")

        Returns:
            True if monitoring started, False if disabled
        """
        with self._lock:
            # Check if monitoring is enabled (single decision point)
            if not self._app_context.settings.get_auto_reconnect_enabled():
                logger.info(f"[MonitoringService] Disabled (battery saver mode) - session {session_id}")
                self._is_running = False
                return False

            self._session_id = session_id
            self._is_running = True

        # Start passive log monitor (all modes) — tails BOTH core logs
        self._log_monitor.start()

        # Start auto-reconnect session
        self._auto_reconnect.start_session(session_id)

        # Start active monitor in all modes (adaptive lazy probing)
        self._active_monitor.start(transport_type, session_id=session_id)
        logger.info(
            f"[MonitoringService] Started ({mode} mode, session {session_id}, transport={transport_type or 'tcp'})"
        )

        return True

    def stop(self):
        """
        Stop all monitoring services immediately.

        This is a HARD OVERRIDE:
        - Cancels any in-progress reconnect attempts
        - Stops all monitors
        - Invalidates current session
        - ALL subsequent signals will be ignored
        """
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False
            session_id = self._session_id
            self._session_id = 0

        # Order matters: cancel reconnect first, then stop monitors
        self._auto_reconnect.cancel()
        self._active_monitor.stop()
        self._log_monitor.stop()

        logger.info(f"[MonitoringService] Stopped (session {session_id})")

    def handle_failure(self, current_connection: Optional[dict]):
        """
        Trigger reconnect attempt for a detected failure.

        Called by ConnectionManager AFTER it has decided to start reconnect.
        This is the only entry point for reconnect - monitors don't call this.

        Args:
            current_connection: Current connection info dict
        """
        with self._lock:
            if not self._is_running:
                logger.debug("[MonitoringService] Reconnect ignored (not running)")
                return
            session_id = self._session_id

        self._auto_reconnect.handle_failure(current_connection, session_id)

    def _mode_aware_internet_check(self, current_connection: Optional[dict]) -> bool:
        """Check physical internet availability before attempting reconnect.

        Validates physical network reachability (gateway/DNS) rather than probing
        the dead tunnel, eliminating the Catch-22 failure abort loop.
        """
        return self._network_validator.check_internet_connection()

    @property
    def session_id(self) -> int:
        """Get current session ID (0 if not running)."""
        with self._lock:
            return self._session_id if self._is_running else 0

    @property
    def network_validator(self):
        """Get the NetworkValidator instance (for pre-connection checks)."""
        return self._network_validator
