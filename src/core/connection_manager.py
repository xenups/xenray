"""Connection Manager."""

import asyncio
import json
import time
from typing import Optional

from loguru import logger

from src.core.config_manager import ConfigManager
from src.core.constants import OUTPUT_CONFIG_PATH
from src.core.i18n import t
from src.services.network_stability_observer import NetworkStabilityObserver
from src.services.passive_log_monitor import PassiveLogMonitor
from src.services.singbox_service import SingboxService
from src.services.xray_service import XrayService


class ConnectionManager:
    """Manages VPN/Proxy connections."""

    def __init__(self, config_manager: ConfigManager):
        """Initialize ConnectionManager with injected dependencies (DIP)."""
        self._config_manager = config_manager

        # Initialize services (Dependency Injection)
        from src.services.configuration_processor import ConfigurationProcessor
        from src.services.network_validator import NetworkValidator
        from src.services.routing_rules_manager import RoutingRulesManager
        from src.services.xray_config_processor import XrayConfigProcessor

        self._config_processor = ConfigurationProcessor(config_manager)
        self._network_validator = NetworkValidator()
        self._xray_processor = XrayConfigProcessor(config_manager)
        self._routing_manager = RoutingRulesManager(config_manager)

        self._xray_service = XrayService()
        self._singbox_service = SingboxService()

        # Initialize network stability observer for monitoring
        self._observer = NetworkStabilityObserver()
        logger.info("[ConnectionManager] Network stability observer initialized")

        # Initialize passive log monitor if observer is available
        self._log_monitor: Optional[PassiveLogMonitor] = None
        if self._observer:
            self._log_monitor = PassiveLogMonitor(self._observer)
            logger.info("[ConnectionManager] Passive log monitor initialized")

        self._current_connection = None

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
        # Check rate limit (VPN only)
        if not self._check_rate_limit(mode, step_callback):
            return False

        try:
            # Load and validate configuration
            config = self._load_and_validate_config(file_path, mode, step_callback)
            if not config:
                return False

            # Pre-connection checks
            if not self._pre_connection_checks(mode, step_callback):
                return False

            # Process configuration
            processed_config, socks_port = self._prepare_configuration(config, step_callback)
            if not processed_config:
                return False

            # Start Xray service
            xray_pid = self._start_xray(mode, step_callback)
            if not xray_pid:
                return False

            # Start Sing-box if VPN mode
            singbox_pid = None
            if mode == "vpn":
                singbox_pid = self._start_singbox(processed_config, socks_port, mode, step_callback)
                if not singbox_pid:
                    self._xray_service.stop()
                    return False

            # Finalize connection
            self._finalize_connection(file_path, mode, xray_pid, singbox_pid, step_callback)
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._report_failure(mode)
            return False

    def _check_rate_limit(self, mode: str, step_callback) -> bool:
        """Check rate limit for VPN connections."""
        if mode != "vpn" or not self._rate_limiter:
            return True

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(self._rate_limiter._throttle.limit("vpn_connection", cost=1))

        if result.limited:
            retry_after = result.retry_after or 1.0
            logger.warning(f"[ConnectionManager] Connection rate limited. Retry after {retry_after:.1f}s")
            if step_callback:
                step_callback(f"Rate limited - waiting {retry_after:.1f}s...")
            time.sleep(retry_after)

        return True

    def _load_and_validate_config(self, file_path: str, mode: str, step_callback) -> Optional[dict]:
        """Load and validate configuration file."""
        if step_callback:
            step_callback(t("status.loading_config"))

        logger.debug(f"Loading config from {file_path}")
        config, _ = self._config_manager.load_config(file_path)

        if not config:
            logger.error("Failed to load config")
            self._report_failure(mode)
            return None

        if not isinstance(config, dict):
            logger.error(f"Invalid config format: expected dict, got {type(config).__name__}")
            if step_callback:
                step_callback(t("status.invalid_config"))
            self._report_failure(mode)
            return None

        return config

    def _pre_connection_checks(self, mode: str, step_callback) -> bool:
        """Perform pre-connection checks using NetworkValidator."""
        # Check internet connectivity
        if step_callback:
            step_callback(t("connection.checking_network"))

        if not self._network_validator.check_internet_connection():
            logger.error("No internet connection detected")
            if step_callback:
                step_callback(t("connection.no_internet"))
            self._report_failure(mode)
            return False

        # Stop existing connection
        if self._current_connection:
            if step_callback:
                step_callback(t("connection.stopping_existing"))
            logger.debug("Stopping existing connection")

            if self._current_connection.get("xray_pid"):
                self._xray_service.stop()
            if self._current_connection.get("singbox_pid"):
                self._singbox_service.stop()

        return True

    def _prepare_configuration(self, config: dict, step_callback) -> tuple[Optional[dict], Optional[int]]:
        """Process and save configuration using XrayConfigProcessor."""
        if step_callback:
            step_callback(t("connection.processing_config"))

        # Delegate to XrayConfigProcessor
        processed_config = self._xray_processor.process_config(config)
        socks_port = self._xray_processor.get_socks_port(processed_config)

        # Save processed config
        logger.debug(f"Saving processed config to {OUTPUT_CONFIG_PATH}")
        try:
            with open(OUTPUT_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(processed_config, f, indent=2)
            logger.debug("Config saved successfully")
        except Exception as e:
            logger.error(f"Failed to save Xray config: {e}")
            return None, None

        return processed_config, socks_port

    def _start_xray(self, mode: str, step_callback) -> Optional[int]:
        """Start Xray service."""
        if step_callback:
            step_callback(t("connection.starting_xray"))

        logger.debug("Starting Xray service")
        xray_pid = self._xray_service.start(OUTPUT_CONFIG_PATH)

        if not xray_pid:
            logger.error("Failed to start Xray")
            self._report_failure(mode)
            return None

        logger.debug(f"Xray started with PID {xray_pid}")
        return xray_pid

    def _start_singbox(self, processed_config: dict, socks_port: int, mode: str, step_callback) -> Optional[int]:
        """Start Sing-box service for VPN mode using XrayConfigProcessor."""
        if step_callback:
            step_callback(t("connection.initializing_vpn"))

        from src.utils.network_utils import NetworkUtils

        # Detect MTU using XrayConfigProcessor
        is_quic = self._xray_processor.is_quic_transport(processed_config)
        mtu_mode = "quic_safe" if is_quic else "auto"
        optimal_mtu = NetworkUtils.detect_optimal_mtu(mtu_mode=mtu_mode)
        logger.info(f"Using MTU for TUN interface: {optimal_mtu}")

        # Get routing configuration using XrayConfigProcessor
        routing_country = self._config_manager.get_routing_country()
        proxy_server_ip = self._xray_processor.get_proxy_server_ip(processed_config)
        routing_rules = self._config_manager.load_routing_rules()

        # Start Sing-box
        singbox_pid = self._singbox_service.start(
            xray_socks_port=socks_port,
            proxy_server_ip=proxy_server_ip,
            routing_country=routing_country,
            routing_rules=routing_rules,
            mtu=optimal_mtu,
        )

        if not singbox_pid:
            logger.error("Failed to start Sing-box")
            self._report_failure(mode)
            return None

        return singbox_pid

    def _finalize_connection(self, file_path: str, mode: str, xray_pid: int, singbox_pid: Optional[int], step_callback):
        """Finalize connection and start monitoring."""
        if step_callback:
            step_callback(t("connection.finalizing"))

        self._current_connection = {
            "mode": mode,
            "xray_pid": xray_pid,
            "singbox_pid": singbox_pid,
            "file": file_path,
        }
        logger.info(f"Successfully connected in {mode} mode")

        # Start passive log monitoring (VPN only)
        if mode == "vpn" and self._log_monitor:
            from src.core.constants import SINGBOX_LOG_FILE, XRAY_LOG_FILE

            self._log_monitor.start_monitoring([XRAY_LOG_FILE, SINGBOX_LOG_FILE])

        # Report success to rate limiter (VPN only)
        if mode == "vpn" and self._rate_limiter:
            self._rate_limiter.report_success()

    def _report_failure(self, mode: str):
        """Report connection failure to rate limiter."""
        if mode == "vpn" and self._rate_limiter:
            self._rate_limiter.report_failure()

    def disconnect(self) -> bool:
        """Disconnect current connection."""
        if not self._current_connection:
            return True

        # Stop passive log monitoring
        if self._log_monitor:
            self._log_monitor.stop_monitoring()

        # Stop Sing-box first
        if self._current_connection.get("singbox_pid"):
            self._singbox_service.stop()

        # Stop Xray
        if self._current_connection["xray_pid"]:
            self._xray_service.stop()

        self._current_connection = None
        return True
