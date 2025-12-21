"""Connection Manager - Facade for connection management."""

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
        from src.services.network_validator import NetworkValidator
        from src.services.routing_rules_manager import RoutingRulesManager
        from src.services.xray_config_processor import XrayConfigProcessor

        config_processor = ConfigurationProcessor(config_manager)
        network_validator = NetworkValidator()
        xray_processor = XrayConfigProcessor(config_manager)
        routing_manager = RoutingRulesManager(config_manager)

        xray_service = XrayService()
        singbox_service = SingboxService()

        # Create ConnectionOrchestrator with all dependencies
        self._orchestrator = ConnectionOrchestrator(
            config_manager=config_manager,
            config_processor=config_processor,
            network_validator=network_validator,
            xray_processor=xray_processor,
            routing_manager=routing_manager,
            xray_service=xray_service,
            singbox_service=singbox_service,
            observer=None,
            log_monitor=None,
        )
        self._current_connection = None

        # Connection Adoption: Check if services are already running (CLI persistence)
        self._adopt_existing_connection()

    def _adopt_existing_connection(self):
        """Adopt an already running connection (from PID files)."""
        xray_pid = self._orchestrator._xray_service.pid
        singbox_pid = self._orchestrator._singbox_service.pid

        if xray_pid:
            # We have at least Xray running
            mode = "vpn" if singbox_pid else "proxy"
            self._current_connection = {
                "mode": mode,
                "xray_pid": xray_pid,
                "singbox_pid": singbox_pid,
                "file": "Adopted Connection",
            }
            logger.debug(f"[ConnectionManager] Adopted existing {mode} connection")

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
        # Stop existing connection if any
        if self._current_connection:
            logger.debug("Stopping existing connection before new connection")
            self._orchestrator.teardown_connection(self._current_connection)
            self._current_connection = None

        # Delegate to orchestrator
        success, connection_info = self._orchestrator.establish_connection(file_path, mode, step_callback)

        if success:
            self._current_connection = connection_info
            logger.info(f"[ConnectionManager] Connection established in {mode} mode")

        return success

    def disconnect(self) -> bool:
        """Disconnect current connection."""
        if not self._current_connection:
            return True

        # Delegate to orchestrator
        self._orchestrator.teardown_connection(self._current_connection)
        self._current_connection = None

        logger.info("[ConnectionManager] Disconnected successfully")
        return True
