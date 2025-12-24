"""Connection Manager - Facade for connection management."""

import threading

from loguru import logger

from src.core.config_manager import ConfigManager
from src.core.connection_orchestrator import ConnectionOrchestrator
from src.services.singbox_service import SingboxService
from src.services.xray_service import XrayService


class ConnectionManager:
    """Facade for VPN/Proxy connection management."""

    def __init__(self, config_manager: ConfigManager):
        """Initialize ConnectionManager with injected dependencies (DIP)."""

        # Initialize services (Dependency Injection)
        from src.services.configuration_processor import ConfigurationProcessor
        from src.services.legacy_config_service import LegacyConfigService
        from src.services.network_validator import NetworkValidator
        from src.services.routing_rules_manager import RoutingRulesManager
        from src.services.xray_config_processor import XrayConfigProcessor
        from src.services.passive_log_monitor import PassiveLogMonitor
        from src.services.auto_reconnect_service import AutoReconnectService
        from src.services.connection_tester import ConnectionTester
        from src.services.active_connectivity_monitor import ActiveConnectivityMonitor
        from src.services.singbox_metrics_provider import ClashAPIProvider

        self._config_manager = config_manager
        config_processor = ConfigurationProcessor(config_manager)
        self._network_validator = NetworkValidator()
        xray_processor = XrayConfigProcessor(config_manager)
        routing_manager = RoutingRulesManager(config_manager)
        legacy_config_service = LegacyConfigService(xray_processor)

        xray_service = XrayService()
        singbox_service = SingboxService()

        # State
        self._current_connection = None
        self._reconnect_event_listener = None
        self._state_lock = threading.Lock()

        # Initialize Auto-Reconnect Service (SRP: separate reconnect logic)
        self._auto_reconnect = AutoReconnectService(
            network_validator=self._network_validator,
            config_loader=config_manager.load_config,
            connection_tester=ConnectionTester,
            connect_fn=self._reconnect_internal,
            event_emitter=self._emit_reconnect_event,
        )
        
        # Initialize Passive Monitor (log-based)
        self._log_monitor = PassiveLogMonitor(
            on_failure_callback=self._handle_passive_failure
        )
        
        # Initialize Active Connectivity Monitor (metrics-based, VPN mode only)
        self._metrics_provider = ClashAPIProvider(port=9090)
        self._active_monitor = ActiveConnectivityMonitor(
            metrics_provider=self._metrics_provider,
            on_connectivity_lost=self._handle_active_connectivity_lost,
            on_connectivity_restored=self._handle_active_connectivity_restored,
        )

        # Create ConnectionOrchestrator with all dependencies
        self._orchestrator = ConnectionOrchestrator(
            config_manager=config_manager,
            config_processor=config_processor,
            network_validator=self._network_validator,
            xray_processor=xray_processor,
            routing_manager=routing_manager,
            xray_service=xray_service,
            singbox_service=singbox_service,
            legacy_config_service=legacy_config_service,
            observer=None,
            log_monitor=self._log_monitor,
        )

        # Connection Adoption: Check if services are already running (CLI persistence)
        self._adopt_existing_connection()

    def _adopt_existing_connection(self):
        """Adopt an already running connection (from PID files)."""
        xray_pid = self._orchestrator._xray_service.pid
        singbox_pid = self._orchestrator._singbox_service.pid

        if xray_pid:
            mode = "vpn" if singbox_pid else "proxy"
            self._current_connection = {
                "mode": mode,
                "xray_pid": xray_pid,
                "singbox_pid": singbox_pid,
                "file": "Adopted Connection",
            }
            logger.debug(f"[ConnectionManager] Adopted existing {mode} connection")
            self._log_monitor.start()

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
        with self._state_lock:
            if self._current_connection:
                logger.debug("Stopping existing connection before new connection")
                self._orchestrator.teardown_connection(self._current_connection)
                self._current_connection = None
                self._active_monitor.stop()

        success, connection_info = self._orchestrator.establish_connection(file_path, mode, step_callback)

        with self._state_lock:
            if success:
                self._current_connection = connection_info
                logger.info(f"[ConnectionManager] Connection established in {mode} mode")
                
                # Start active monitor for VPN mode only
                if mode == "vpn":
                    self._active_monitor.start()

        return success

    def _reconnect_internal(self, file_path: str, mode: str) -> bool:
        """Internal reconnect method for AutoReconnectService (no step_callback)."""
        return self.connect(file_path, mode, step_callback=None)

    def disconnect(self) -> bool:
        """Disconnect current connection."""
        with self._state_lock:
            if not self._current_connection:
                return True
            connection = self._current_connection
            self._current_connection = None

        # Stop monitors
        self._active_monitor.stop()
        
        self._orchestrator.teardown_connection(connection)
        logger.info("[ConnectionManager] Disconnected successfully")
        return True

    def set_reconnect_event_listener(self, callback):
        """
        Set a callback to be notified of passive reconnect events.
        
        Args:
            callback: Function that accepts (event_type: str, data: dict)
        """
        self._reconnect_event_listener = callback

    def _emit_reconnect_event(self, event_type: str, data: dict = None):
        """Emit a reconnect event to the listener."""
        if self._reconnect_event_listener:
            try:
                self._reconnect_event_listener(event_type, data or {})
            except Exception as e:
                logger.error(f"[ConnectionManager] Error in reconnect event listener: {e}")

    def _handle_passive_failure(self):
        """Callback triggered when PassiveLogMonitor detects a connection failure."""
        with self._state_lock:
            current_conn = self._current_connection
        
        # Delegate to AutoReconnectService (SRP)
        self._auto_reconnect.handle_failure(current_conn)

    def _handle_active_connectivity_lost(self):
        """Callback triggered when ActiveConnectivityMonitor detects connectivity loss."""
        logger.warning("[ConnectionManager] Active monitor: connectivity lost")
        self._emit_reconnect_event("connectivity_lost")
        
        with self._state_lock:
            current_conn = self._current_connection
        
        # Delegate to AutoReconnectService (SRP)
        self._auto_reconnect.handle_failure(current_conn)

    def _handle_active_connectivity_restored(self):
        """Callback triggered when ActiveConnectivityMonitor detects connectivity restored."""
        logger.info("[ConnectionManager] Active monitor: connectivity restored")
        self._emit_reconnect_event("connectivity_restored")

