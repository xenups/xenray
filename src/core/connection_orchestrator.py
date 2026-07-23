"""Connection Orchestrator - Coordinates connection workflow."""

import json
from typing import Optional

from loguru import logger

from src.core.constants import MODE_VPN, OUTPUT_CONFIG_PATH
from src.core.i18n import t
from src.core.types import TunEngine
from src.services.singbox_tun_service import SingboxTunService


class ConnectionOrchestrator:
    """Orchestrates connection establishment and teardown workflow."""

    def __init__(
        self,
        app_context,
        network_validator,
        xray_processor,
        xray_service,
        legacy_config_service,
    ):
        """
        Initialize ConnectionOrchestrator with injected dependencies.

        Args:
            app_context: AppContext instance
            network_validator: NetworkValidator instance
            xray_processor: XrayConfigProcessor instance
            xray_service: XrayService instance
            legacy_config_service: LegacyConfigService instance

        NOTE: Monitoring (log_monitor, active_monitor, auto_reconnect) is handled
              by ConnectionMonitoringService in ConnectionManager.
        """
        self._app_context = app_context
        self._network_validator = network_validator
        self._xray_processor = xray_processor
        self._xray_service = xray_service
        self._legacy_config_service = legacy_config_service
        self._singbox_tun: Optional[SingboxTunService] = None

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

                # Process configuration (TUN inbound is injected here for VPN mode)
                processed_config, socks_port = self._prepare_configuration(config, mode, step_callback)
                if not processed_config:
                    continue

                # Start Xray service (single process handles both proxy and VPN/TUN)
                xray_pid = self._start_xray(step_callback)
                if not xray_pid:
                    continue

                # Start sing-box TUN if VPN mode with sing-box engine
                if mode == MODE_VPN and self._is_singbox_engine():
                    if step_callback:
                        step_callback(t("connection.initializing_vpn"))
                    tun_pid = self._start_singbox_tun(socks_port, processed_config)
                    if not tun_pid:
                        logger.error("[ConnectionOrchestrator] Failed to start sing-box TUN")
                        self.teardown_connection({"xray_pid": xray_pid})
                        continue
                    logger.info(f"[ConnectionOrchestrator] Sing-box TUN started (PID: {tun_pid})")

                # Verify connection health
                if self._verify_connection_health(processed_config, step_callback, mode, socks_port):
                    connection_info = self._finalize_connection(file_path, mode, xray_pid, step_callback)
                    return True, connection_info
                else:
                    logger.error(f"[ConnectionOrchestrator] {label.capitalize()} config failed health check")
                    self.teardown_connection({"xray_pid": xray_pid})

            logger.error("[ConnectionOrchestrator] All connection attempts failed")
            return False, None

        except Exception as e:
            logger.error(f"Connection orchestration failed: {e}")
            return False, None

    def _verify_connection_health(
        self, config: dict, step_callback, mode: str = "proxy", health_socks_port: int = 0
    ) -> bool:
        """Verify the connection is actually working before declaring success."""
        if step_callback:
            step_callback(t("connection.verifying_latency"))

        from src.services.connection_tester import ConnectionTester

        # In proxy mode use the SOCKS port.
        # In VPN mode traffic goes through TUN, so socks_port=0 is fine
        # (the tester will use a direct HTTP probe through the TUN interface).
        socks_port = health_socks_port if (mode == "proxy" and health_socks_port > 0) else 0
        if socks_port:
            logger.debug(
                f"[ConnectionOrchestrator] Routing health check through existing SOCKS proxy port {socks_port}"
            )

        success, latency, _ = ConnectionTester.test_connection_sync(config, socks_port=socks_port)

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
        # Stop sing-box TUN first (if running) before stopping Xray
        if self._singbox_tun and self._singbox_tun.is_running():
            logger.info("[ConnectionOrchestrator] Stopping active sing-box TUN instance...")
            self._singbox_tun.stop()
            self._singbox_tun = None
        else:
            # Check if an adopted sing-box TUN process is running
            orphan_svc = SingboxTunService()
            if orphan_svc.is_running():
                logger.info("[ConnectionOrchestrator] Stopping adopted sing-box TUN process...")
                orphan_svc.stop()

        # Stop Xray (single process — handles both proxy and TUN)
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
        if step_callback:
            step_callback(t("connection.checking_network"))

        if not self._network_validator.check_internet_connection():
            logger.error("No internet connection detected")
            if step_callback:
                step_callback(t("connection.no_internet"))
            return False

        return True

    def _prepare_configuration(self, config: dict, mode: str, step_callback) -> tuple[Optional[dict], Optional[int]]:
        """
        Process and save configuration using XrayConfigProcessor.

        For VPN mode, inject_tun_inbound() is called inside process_config().
        """
        if step_callback:
            step_callback(t("connection.processing_config"))

        # Delegate to XrayConfigProcessor (mode="vpn" triggers TUN injection)
        processed_config = self._xray_processor.process_config(config, mode=mode)
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

    def _is_singbox_engine(self) -> bool:
        """Check if the sing-box TUN engine is selected."""
        return self._app_context.settings.get_tun_engine() == str(TunEngine.SING_BOX)

    def _start_singbox_tun(self, socks_port: int, config: dict) -> Optional[int]:
        """Start sing-box TUN service pointing to Xray SOCKS proxy."""
        from src.utils.network_utils import NetworkUtils

        routing_country = self._app_context.settings.get_routing_country()
        routing_rules = self._app_context.routing.load_rules()
        proxy_server_ips = self._xray_processor.get_proxy_server_ip(config)
        mtu = NetworkUtils.detect_optimal_mtu(mtu_mode="auto")

        self._singbox_tun = SingboxTunService()
        return self._singbox_tun.start(
            xray_socks_port=socks_port,
            proxy_server_ip=proxy_server_ips,
            routing_country=routing_country,
            routing_rules=routing_rules,
            mtu=mtu,
        )

    def _finalize_connection(
        self,
        file_path: str,
        mode: str,
        xray_pid: int,
        step_callback,
    ) -> dict:
        """Finalize connection and return connection info."""
        if step_callback:
            step_callback(t("connection.finalizing"))

        connection_info = {
            "mode": mode,
            "xray_pid": xray_pid,
            "file": file_path,
        }

        # NOTE: Monitoring is now started by ConnectionManager via ConnectionMonitoringService
        # after this method returns. This ensures single decision point for monitoring.

        logger.info(f"Successfully connected in {mode} mode")

        return connection_info
