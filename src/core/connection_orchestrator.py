"""Connection Orchestrator - Coordinates connection workflow."""

import json
from typing import Optional

from loguru import logger

from src.core.constants import OUTPUT_CONFIG_PATH
from src.core.i18n import t


class ConnectionOrchestrator:
    """Orchestrates connection establishment and teardown workflow."""

    def __init__(
        self,
        app_context,
        network_validator,
        xray_processor,
        xray_service,
        singbox_service,
        legacy_config_service,
    ):
        """
        Initialize ConnectionOrchestrator with injected dependencies.

        Args:
            app_context: AppContext instance
            network_validator: NetworkValidator instance
            xray_processor: XrayConfigProcessor instance
            xray_service: XrayService instance
            singbox_service: SingboxService instance
            legacy_config_service: LegacyConfigService instance

        NOTE: Monitoring (log_monitor, active_monitor, auto_reconnect) is handled
              by ConnectionMonitoringService in ConnectionManager.
        """
        self._app_context = app_context
        self._network_validator = network_validator
        self._xray_processor = xray_processor
        self._xray_service = xray_service
        self._singbox_service = singbox_service
        self._legacy_config_service = legacy_config_service

    def establish_connection(self, file_path: str, mode: str, step_callback=None) -> tuple[bool, Optional[dict]]:
        """
        Orchestrate full connection workflow with legacy migration and fallback.

        Args:
            file_path: Path to configuration file
            mode: Connection mode ("vpn" or "proxy")
            step_callback: Optional callback for connection steps

        Returns:
            (success, connection_info) tuple
        """
        try:
            # 1. Load and validate configuration
            original_config = self._load_and_validate_config(file_path, step_callback)
            if not original_config:
                return False, None

            # 2. Check if migration is needed and prepare migrated config
            is_legacy = self._legacy_config_service.is_legacy(original_config)
            configs_to_try = []

            if is_legacy:
                logger.info("[ConnectionOrchestrator] Legacy config detected, preparing migration")
                migrated_config = self._legacy_config_service.migrate_config(original_config)
                configs_to_try.append(("migrated", migrated_config))
                configs_to_try.append(("original", original_config))
            else:
                configs_to_try.append(("standard", original_config))

            # 3. Pre-connection checks
            if not self._pre_connection_checks(step_callback):
                return False, None

            # 4. Attempt connection with retry/fallback
            for label, config in configs_to_try:
                if label == "original":
                    logger.warning("[ConnectionOrchestrator] Falling back to original legacy configuration")
                    if step_callback:
                        step_callback(t("connection.falling_back"))

                # Process configuration
                processed_config, socks_port = self._prepare_configuration(config, step_callback)
                if not processed_config:
                    continue

                # Start Xray service
                xray_pid = self._start_xray(step_callback)
                if not xray_pid:
                    continue

                # Start Sing-box if VPN mode
                singbox_pid = None
                if mode == "vpn":
                    singbox_pid = self._start_singbox(processed_config, socks_port, step_callback)
                    if not singbox_pid:
                        self._xray_service.stop()
                        continue

                # Verify connection health
                if self._verify_connection_health(processed_config, step_callback):
                    # Finalize connection
                    connection_info = self._finalize_connection(file_path, mode, xray_pid, singbox_pid, step_callback)
                    return True, connection_info
                else:
                    logger.error(f"[ConnectionOrchestrator] {label.capitalize()} config failed health check")
                    self.teardown_connection({"xray_pid": xray_pid, "singbox_pid": singbox_pid})

            logger.error("[ConnectionOrchestrator] All connection attempts failed")
            return False, None

        except Exception as e:
            logger.error(f"Connection orchestration failed: {e}")
            return False, None

    def _verify_connection_health(self, config: dict, step_callback) -> bool:
        """Verify the connection is actually working before declaring success."""
        if step_callback:
            step_callback(t("connection.verifying_latency"))

        from src.services.connection_tester import ConnectionTester

        # Run a quick sync test (since we are already in the orchestrator thread)
        success, latency, _ = ConnectionTester.test_connection_sync(config)

        if success:
            logger.info(f"[ConnectionOrchestrator] Connection verified: {latency}")
            return True

        logger.warning(f"[ConnectionOrchestrator] Connection verification failed: {latency}")
        return False

    def teardown_connection(self, connection_info: dict):
        """
        Tear down active connection.

        Args:
            connection_info: Connection information dictionary

        NOTE: Monitoring is stopped by ConnectionManager via ConnectionMonitoringService
              before this method is called.
        """
        # Stop Sing-box first
        if connection_info.get("singbox_pid"):
            self._singbox_service.stop()

        # Stop Xray
        if connection_info.get("xray_pid"):
            self._xray_service.stop()

        logger.info("Connection torn down successfully")

    def _load_and_validate_config(self, file_path: str, step_callback) -> Optional[dict]:
        """Load and validate configuration file."""
        if step_callback:
            step_callback(t("status.loading_config"))

        logger.debug(f"Loading config from {file_path}")
        config, _ = self._app_context.load_config(file_path)

        if not config:
            logger.error("Failed to load config")
            return None

        if not isinstance(config, dict):
            logger.error(f"Invalid config format: expected dict, got {type(config).__name__}")
            if step_callback:
                step_callback(t("status.invalid_config"))
            return None

        return config

    def _pre_connection_checks(self, step_callback) -> bool:
        """Perform pre-connection checks using NetworkValidator."""
        # Check internet connectivity
        if step_callback:
            step_callback(t("connection.checking_network"))

        if not self._network_validator.check_internet_connection():
            logger.error("No internet connection detected")
            if step_callback:
                step_callback(t("connection.no_internet"))
            return False

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

    def _start_xray(self, step_callback) -> Optional[int]:
        """Start Xray service."""
        if step_callback:
            step_callback(t("connection.starting_xray"))

        logger.debug("Starting Xray service")
        xray_pid = self._xray_service.start(OUTPUT_CONFIG_PATH)

        if not xray_pid:
            logger.error("Failed to start Xray")
            return None

        logger.debug(f"Xray started with PID {xray_pid}")
        return xray_pid

    def _start_singbox(self, processed_config: dict, socks_port: int, step_callback) -> Optional[int]:
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
        routing_country = self._app_context.settings.get_routing_country()
        proxy_server_ip = self._xray_processor.get_proxy_server_ip(processed_config)
        routing_rules = self._app_context.routing.load_rules()

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
            return None

        return singbox_pid

    def _finalize_connection(
        self,
        file_path: str,
        mode: str,
        xray_pid: int,
        singbox_pid: Optional[int],
        step_callback,
    ) -> dict:
        """Finalize connection and return connection info."""
        if step_callback:
            step_callback(t("connection.finalizing"))

        connection_info = {
            "mode": mode,
            "xray_pid": xray_pid,
            "singbox_pid": singbox_pid,
            "file": file_path,
        }

        # NOTE: Monitoring is now started by ConnectionManager via ConnectionMonitoringService
        # after this method returns. This ensures single decision point for monitoring.

        logger.info(f"Successfully connected in {mode} mode")

        return connection_info
