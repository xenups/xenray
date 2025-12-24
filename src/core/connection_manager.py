"""Connection Manager - Facade for connection management with session-scoped lifecycle."""

import threading

from loguru import logger

from src.core.config_manager import ConfigManager
from src.core.i18n import t
from src.core.connection_orchestrator import ConnectionOrchestrator
from src.services.singbox_service import SingboxService
from src.services.xray_service import XrayService


class ConnectionManager:
    """
    Facade for VPN/Proxy connection management.

    Signal-Based Architecture:
    - Monitors emit SIGNALS (facts) - no event semantics
    - ConnectionManager is the SINGLE EVENT AUTHORITY
    - All signals are converted to events here
    - All late signals after disconnect are ignored here

    Session-Scoped Lifecycle:
    - Each connection has a unique session_id
    - Disconnect is TERMINAL: cancels all reconnect, monitoring, background tasks
    - No stale events can be emitted after disconnect

    State Machine: IDLE → CONNECTING → CONNECTED → (RECONNECTING) → DISCONNECTING → IDLE
    """

    def __init__(self, config_manager: ConfigManager):
        """Initialize ConnectionManager with injected dependencies (DIP)."""

        # Initialize services (Dependency Injection)
        from src.services.configuration_processor import ConfigurationProcessor
        from src.services.legacy_config_service import LegacyConfigService
        from src.services.routing_rules_manager import RoutingRulesManager
        from src.services.xray_config_processor import XrayConfigProcessor
        from src.services.monitoring import ConnectionMonitoringService, MonitorSignal

        # Store MonitorSignal for use in signal handler
        self._MonitorSignal = MonitorSignal

        self._config_manager = config_manager
        config_processor = ConfigurationProcessor(config_manager)
        self._xray_processor = XrayConfigProcessor(config_manager)
        routing_manager = RoutingRulesManager(config_manager)
        legacy_config_service = LegacyConfigService(self._xray_processor)

        xray_service = XrayService()
        singbox_service = SingboxService()

        # State
        self._current_connection = None
        self._reconnect_event_listener = None
        self._state_lock = threading.Lock()
        self._session_id = 0  # Unique ID for each connection session

        # Initialize ConnectionMonitoringService (creates its own monitors internally)
        # Only 3 callbacks needed:
        # - on_signal: Unified signal handler (this class is the event authority)
        # - on_reconnect: Called when reconnect attempt is needed
        # - on_reconnect_event: For reconnect-specific events (reconnecting, reconnected, etc.)
        self._monitoring = ConnectionMonitoringService(
            config_manager=config_manager,
            on_signal=self._handle_signal,
            on_reconnect=self._reconnect_internal,
            on_reconnect_event=self._emit_event,
        )

        # Create ConnectionOrchestrator with all dependencies
        self._orchestrator = ConnectionOrchestrator(
            config_manager=config_manager,
            config_processor=config_processor,
            network_validator=self._monitoring.network_validator,
            xray_processor=self._xray_processor,
            routing_manager=routing_manager,
            xray_service=xray_service,
            singbox_service=singbox_service,
            legacy_config_service=legacy_config_service,
        )

        # Connection Adoption: Check if services are already running (CLI persistence)
        self._adopt_existing_connection()

    def _handle_signal(self, signal):
        """
        Handle monitor signals - SINGLE POINT OF SIGNAL→EVENT CONVERSION.

        This is the ONLY place where signals become user-visible events.
        All policy decisions (emit event? trigger reconnect?) happen here.

        Args:
            signal: MonitorSignal enum value
        """
        # Get current connection state (thread-safe)
        with self._state_lock:
            current_conn = self._current_connection
            session_valid = self._session_id > 0

        # CRITICAL: Ignore all signals if no valid session
        # This prevents late signals after disconnect
        if not session_valid or not current_conn:
            logger.debug(f"[ConnectionManager] Signal {signal.name} ignored (no valid session)")
            return

        # SIGNAL → EVENT MAPPING (single source of truth)
        if signal == self._MonitorSignal.PASSIVE_FAILURE:
            # Passive log detected failure - trigger reconnect
            logger.warning("[ConnectionManager] Passive failure detected")
            self._monitoring.handle_failure(current_conn)

        elif signal == self._MonitorSignal.ACTIVE_LOST:
            # Active monitor detected connectivity loss
            logger.warning("[ConnectionManager] Active monitor: connectivity lost")
            self._emit_event("connectivity_lost")
            self._monitoring.handle_failure(current_conn)

        elif signal == self._MonitorSignal.ACTIVE_DEGRADED:
            # Active monitor detected degradation (soft warning - no reconnect)
            logger.info("[ConnectionManager] Active monitor: connectivity degraded")
            self._emit_event("connectivity_degraded")

        elif signal == self._MonitorSignal.ACTIVE_RESTORED:
            # Active monitor detected recovery
            logger.info("[ConnectionManager] Active monitor: connectivity restored")
            self._emit_event("connectivity_restored")

    def _adopt_existing_connection(self):
        """Adopt an already running connection (from PID files)."""
        xray_pid = self._orchestrator._xray_service.pid
        singbox_pid = self._orchestrator._singbox_service.pid

        if xray_pid:
            mode = "vpn" if singbox_pid else "proxy"
            self._session_id += 1
            self._current_connection = {
                "mode": mode,
                "xray_pid": xray_pid,
                "singbox_pid": singbox_pid,
                "file": t("connection.adopted_connection", default="Adopted Connection"),
                "session_id": self._session_id,
            }
            logger.debug(f"[ConnectionManager] Adopted existing {mode} connection (session {self._session_id})")

            # Start monitoring via facade (single decision point)
            self._monitoring.start(self._session_id, mode=mode)

    def connect(self, file_path: str, mode: str, step_callback=None) -> bool:
        """
        Establish connection using specified configuration file.

        Args:
            file_path: Path to configuration file
            mode: Connection mode ("vpn" or "proxy")
            step_callback: Optional callback for connection steps

        Returns:
            True if connection successful, False otherwise
        """
        # Emit connecting state
        self._emit_event("connecting")

        with self._state_lock:
            if self._current_connection:
                logger.debug("Stopping existing connection before new connection")
                self._monitoring.stop()
                self._orchestrator.teardown_connection(self._current_connection)
                self._current_connection = None

            # Create new session
            self._session_id += 1
            current_session = self._session_id

        success, connection_info = self._orchestrator.establish_connection(file_path, mode, step_callback)

        with self._state_lock:
            # Verify we're still in the same session (not cancelled)
            if self._session_id != current_session:
                logger.warning("[ConnectionManager] Session changed during connect, aborting")
                return False

            if success:
                connection_info["session_id"] = current_session
                self._current_connection = connection_info
                logger.info(f"[ConnectionManager] Connection established in {mode} mode (session {current_session})")

                # Start monitoring via facade (single decision point)
                config, _ = self._config_manager.load_config(file_path)
                transport_type = self._xray_processor.get_transport_type(config) if config else None
                self._monitoring.start(current_session, mode=mode, transport_type=transport_type)

                # Emit connected state
                self._emit_event("connected")
            else:
                self._emit_event("connect_failed")

        return success

    def _reconnect_internal(self, file_path: str, mode: str) -> bool:
        """Internal reconnect method for AutoReconnectService (no step_callback)."""
        return self.connect(file_path, mode, step_callback=None)

    def disconnect(self) -> bool:
        """
        Disconnect current connection.

        This is a HARD OVERRIDE:
        - Immediately cancels all reconnect attempts
        - Stops all monitoring (active and passive)
        - Invalidates current session to prevent late signals/events
        - No automatic restart is possible after this
        """
        # Emit disconnecting state FIRST (user-visible)
        self._emit_event("disconnecting")

        # Stop monitoring via facade (handles all: cancel reconnect, stop monitors)
        # After this, no signals will be forwarded
        self._monitoring.stop()

        with self._state_lock:
            if not self._current_connection:
                self._emit_event("disconnected")
                return True
            connection = self._current_connection
            self._current_connection = None
            # Invalidate session to prevent any late signals
            self._session_id = 0

        # Teardown connection
        self._orchestrator.teardown_connection(connection)
        logger.info("[ConnectionManager] Disconnected successfully (hard override)")

        # Emit final state
        self._emit_event("disconnected")
        return True

    def is_connected(self) -> bool:
        """Check if currently connected."""
        with self._state_lock:
            return self._current_connection is not None

    def get_current_session(self) -> int:
        """Get current session ID (0 if not connected)."""
        with self._state_lock:
            return self._session_id if self._current_connection else 0

    def set_reconnect_event_listener(self, callback):
        """
        Set a callback to be notified of connection state changes.

        Args:
            callback: Function that accepts (event_type: str, data: dict)

        Events:
            - connecting: Connection attempt starting
            - connected: Connection established
            - connect_failed: Connection failed
            - failure_detected: Connection lost (auto-reconnect starting)
            - reconnecting: Auto-reconnect in progress
            - reconnected: Auto-reconnect succeeded
            - reconnect_failed: Auto-reconnect failed
            - connectivity_lost: Active monitor detected stall
            - connectivity_degraded: Soft warning (connection issues)
            - connectivity_restored: Active monitor detected recovery
            - disconnecting: User initiated disconnect
            - disconnected: Disconnect complete
        """
        self._reconnect_event_listener = callback

    def _emit_event(self, event_type: str, data: dict = None):
        """
        Emit a user-visible event to the listener.

        This is the ONLY method that emits events to the UI.
        """
        logger.debug(f"[ConnectionManager] Event: {event_type}")
        if self._reconnect_event_listener:
            try:
                self._reconnect_event_listener(event_type, data or {})
            except Exception as e:
                logger.error(f"[ConnectionManager] Error in event listener: {e}")
