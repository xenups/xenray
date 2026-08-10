"""Connection Orchestrator - Coordinates connection workflow.

Clean-architecture refactor (SRP + DRY) of the connection lifecycle. The public
API (constructor, ``establish_connection``, ``teardown_connection``) is
unchanged; only the internals are decomposed into single-responsibility steps.
"""

import json
from typing import Optional

from loguru import logger

from src.core.constants import CORE_SINGBOX, CORE_XRAY, MODE_PROXY, MODE_VPN, OUTPUT_CONFIG_PATH
from src.core.i18n import t
from src.services.connection_tester import ConnectionTester
from src.utils.network_utils import NetworkUtils
from src.utils.process_utils import purge_all_logs_on_connect


class ConnectionOrchestrator:
    """Orchestrates connection establishment and teardown workflow."""

    # Single-attempt outcomes returned by ``_attempt_single_connection``.
    ATTEMPT_SKIPPED = "skipped"  # config prep or Xray start failed -> try next
    ATTEMPT_ABORTED = "aborted"  # sing-box failed; Xray already stopped -> try next
    ATTEMPT_FAILED = "failed"  # health check failed; resources torn down -> try next
    ATTEMPT_SUCCESS = "success"  # connection established

    def __init__(
        self,
        app_context,
        network_validator,
        xray_processor,
        xray_service,
        legacy_config_service,
        singbox_service=None,
    ):
        """
        Initialize ConnectionOrchestrator with injected dependencies.

        Args:
            app_context: AppContext instance
            network_validator: NetworkValidator instance
            xray_processor: XrayConfigProcessor instance
            xray_service: XrayService instance
            legacy_config_service: LegacyConfigService instance
            singbox_service: Optional SingboxService instance — when set and the
                user selects the sing-box TUN engine, VPN mode runs Xray as the
                proxy and sing-box as the TUN engine (dual-engine).

        NOTE: Monitoring (log_monitor, active_monitor, auto_reconnect) is handled
              by ConnectionMonitoringService in ConnectionManager.
        """
        self._app_context = app_context
        self._network_validator = network_validator
        self._xray_processor = xray_processor
        self._xray_service = xray_service
        self._legacy_config_service = legacy_config_service
        self._singbox_service = singbox_service

    # ------------------------------------------------------------------
    # Engine resolution
    # ------------------------------------------------------------------

    def get_core_engine(self) -> str:
        """Return the active core (proxy) engine. Always 'xray' in XenRay architecture."""
        return CORE_XRAY

    def get_tun_engine(self) -> str:
        """Return the selected TUN engine ('xray' or 'singbox') from settings."""
        return self._resolve_tun_engine()

    def _resolve_tun_engine(self) -> str:
        """Return the selected TUN engine ('xray' or 'singbox') from settings."""
        try:
            engine = self._app_context.settings.get_tun_engine()
        except Exception:
            engine = CORE_SINGBOX
        return engine if engine in (CORE_XRAY, CORE_SINGBOX) else CORE_SINGBOX

    def _uses_singbox_tun(self, mode: str) -> bool:
        """True when VPN mode should use the sing-box TUN engine."""
        if mode != MODE_VPN or self._singbox_service is None:
            return False
        return self.get_tun_engine() == CORE_SINGBOX

    # ------------------------------------------------------------------
    # High-level flow orchestrator
    # ------------------------------------------------------------------

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
            # 0. Clean/purge all log files so each new connection starts with a fresh log slate
            purge_all_logs_on_connect()

            # 1. Load and validate configuration
            original_config = self._load_and_validate_config(file_path, step_callback)
            if not original_config:
                return False, None

            # 2. Build the ordered candidate list (legacy migration + original fallback)
            configs_to_try = self._resolve_candidate_configs(original_config)

            # 3. Pre-connection checks
            if not self._pre_connection_checks(step_callback):
                return False, None

            # 4. Determine engine: sing-box TUN runs Xray (proxy) + sing-box (TUN)
            use_singbox = self._uses_singbox_tun(mode)
            if use_singbox:
                logger.info("[ConnectionOrchestrator] Sing-box TUN engine selected (dual-engine mode)")

            # 5. Attempt each candidate until one succeeds
            for label, config in configs_to_try:
                status, payload = self._attempt_single_connection(
                    label, config, mode, use_singbox, file_path, step_callback
                )
                if status == self.ATTEMPT_SUCCESS:
                    return True, payload

            logger.error("[ConnectionOrchestrator] All connection attempts failed")
            return False, None

        except Exception as e:
            logger.error(f"Connection orchestration failed: {e}")
            return False, None

    # ------------------------------------------------------------------
    # Single-attempt pipeline
    # ------------------------------------------------------------------

    def _attempt_single_connection(
        self,
        label: str,
        config: dict,
        mode: str,
        use_singbox: bool,
        file_path: str,
        step_callback,
    ) -> tuple[str, Optional[dict]]:
        """Run one connection attempt end-to-end.

        Mirrors the original fallback semantics:
        - Config preparation or Xray start failure is a non-fatal skip (the
          original legacy config is tried next when migrating).
        - sing-box start failure stops the just-started Xray proxy.
        - Health-check failure tears the whole attempt down before continuing.

        Returns ``(ATTEMPT_*, connection_info_or_None)``.
        """
        if label == "original":
            logger.warning("[ConnectionOrchestrator] Falling back to original legacy configuration")
            if step_callback:
                step_callback(t("connection.falling_back"))

        xray_pid = None
        singbox_pid = None

        try:
            # Process configuration (TUN inbound is injected here for VPN mode
            # when the Xray engine is active; sing-box TUN only needs the
            # Xray proxy config).
            process_mode = MODE_PROXY if use_singbox else mode
            processed_config, socks_port = self._prepare_configuration(config, process_mode, step_callback)
            if not processed_config:
                return self.ATTEMPT_SKIPPED, None

            # Start Xray service (proxy + VPN/TUN for Xray engine; SOCKS-only
            # proxy for the sing-box TUN engine).
            xray_pid = self._start_xray(step_callback)
            if not xray_pid:
                return self.ATTEMPT_SKIPPED, None

            # Start sing-box TUN engine when selected
            if use_singbox:
                singbox_pid = self._start_singbox(processed_config, socks_port, step_callback)
                if not singbox_pid:
                    self._xray_service.stop()
                    return self.ATTEMPT_ABORTED, None

            # Verify connection health
            if self._verify_connection_health(processed_config, step_callback, socks_port):
                # When LAN sharing is enabled, open the firewall for LAN devices.
                self._ensure_lan_firewall_rule(socks_port)
                connection_info = self._finalize_connection(file_path, mode, xray_pid, singbox_pid, step_callback)
                return self.ATTEMPT_SUCCESS, connection_info

            logger.error(f"[ConnectionOrchestrator] {label.capitalize()} config failed health check")
            self.teardown_connection({"xray_pid": xray_pid, "singbox_pid": singbox_pid})
            return self.ATTEMPT_FAILED, None

        except Exception:
            # Ensure no orphaned PIDs or active TUN adapters remain if an
            # intermediate pipeline step raised unexpectedly.
            logger.warning(f"[ConnectionOrchestrator] Cleaning up resources after failed attempt ({label})")
            self._safe_teardown({"xray_pid": xray_pid, "singbox_pid": singbox_pid})
            raise

    # ------------------------------------------------------------------
    # Candidate resolution (DRY: single source of truth for fallback list)
    # ------------------------------------------------------------------

    def _resolve_candidate_configs(self, original_config: dict) -> list:
        """Build the ordered list of (label, config) candidates to attempt.

        Legacy configs produce [("migrated", migrated), ("original", original)];
        modern configs produce [("standard", original)].
        """
        is_legacy = self._legacy_config_service.is_legacy(original_config)

        if is_legacy:
            logger.info("[ConnectionOrchestrator] Legacy config detected, preparing migration")
            migrated_config = self._legacy_config_service.migrate_config(original_config)
            return [("migrated", migrated_config), ("original", original_config)]

        return [("standard", original_config)]

    # ------------------------------------------------------------------
    # Resource cleanup
    # ------------------------------------------------------------------

    def teardown_connection(self, connection_info: dict):
        """
        Tear down active connection.

        Args:
            connection_info: Connection information dictionary

        NOTE: Monitoring is stopped by ConnectionManager via ConnectionMonitoringService
              before this method is called.
        """
        # Stop sing-box TUN engine first, then Xray proxy.
        if self._singbox_service is not None:
            self._singbox_service.stop()
        self._xray_service.stop()

        # Remove the LAN-sharing firewall rule (idempotent; no-op when not set).
        self._remove_lan_firewall_rule()

        logger.info("Connection torn down successfully")

    def _ensure_lan_firewall_rule(self, socks_port: int) -> None:
        """Create the inbound firewall rule for LAN proxy sharing if enabled.

        Called on a successful connection so LAN devices can reach the SOCKS and
        HTTP proxy ports. Failure is non-fatal (best-effort).
        """
        if not self._app_context.settings.get_allow_lan() or not socks_port:
            return
        try:
            from src.utils.firewall_manager import FirewallManager

            FirewallManager.add_lan_firewall_rule([socks_port, socks_port + 4])
        except Exception as e:
            logger.warning(f"[ConnectionOrchestrator] Failed to apply LAN firewall rule: {e}")

    @staticmethod
    def _remove_lan_firewall_rule() -> None:
        """Remove the LAN-sharing firewall rule (best-effort, never raises)."""
        try:
            from src.utils.firewall_manager import FirewallManager

            FirewallManager.remove_lan_firewall_rule()
        except Exception as e:
            logger.warning(f"[ConnectionOrchestrator] Failed to remove LAN firewall rule: {e}")

    def _safe_teardown(self, connection_info: dict):
        """Teardown that never raises — used from exception cleanup paths."""
        try:
            self.teardown_connection(connection_info)
        except Exception as e:
            logger.error(f"[ConnectionOrchestrator] Teardown after failed attempt raised: {e}")

    # ------------------------------------------------------------------
    # Connection steps (single responsibility helpers)
    # ------------------------------------------------------------------

    def _verify_connection_health(
        self,
        config: dict,
        step_callback,
        health_socks_port: int = 0,
    ) -> bool:
        """Verify the connection is actually working before declaring success."""
        if step_callback:
            step_callback(t("connection.verifying_latency"))

        socks_port = health_socks_port if health_socks_port > 0 else 0
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

    def _load_and_validate_config(self, file_path: str, step_callback) -> Optional[dict]:
        """Load and validate configuration file."""
        if step_callback:
            step_callback(t("connection.loading_config"))

        logger.debug(f"Loading config from {file_path}")
        config, _ = self._app_context.load_config(file_path)

        if not config:
            logger.error("Failed to load config")
            return None

        if not isinstance(config, dict):
            logger.error(f"Invalid config format: expected dict, got {type(config).__name__}")
            if step_callback:
                step_callback(t("connection.invalid_config"))
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

    def _start_singbox(self, processed_config: dict, socks_port: int, step_callback) -> Optional[int]:
        """Start the sing-box TUN engine, routing into Xray's SOCKS proxy."""
        if step_callback:
            step_callback(t("connection.initializing_vpn"))

        # Detect MTU using XrayConfigProcessor
        is_quic = self._xray_processor.is_quic_transport(processed_config)
        mtu_mode = "quic_safe" if is_quic else "auto"
        optimal_mtu = NetworkUtils.detect_optimal_mtu(mtu_mode=mtu_mode)
        logger.info(f"[ConnectionOrchestrator] Using MTU for TUN interface: {optimal_mtu}")

        # Get routing configuration using XrayConfigProcessor
        routing_country = self._app_context.settings.get_routing_country()
        proxy_server_ip = self._xray_processor.get_proxy_server_ip(processed_config)
        routing_rules = self._app_context.routing.load_rules()
        allow_lan = self._app_context.settings.get_allow_lan()

        singbox_pid = self._singbox_service.start(
            xray_socks_port=socks_port,
            proxy_server_ip=proxy_server_ip,
            routing_country=routing_country,
            routing_rules=routing_rules,
            mtu=optimal_mtu,
            allow_lan=allow_lan,
        )

        if not singbox_pid:
            logger.error("[ConnectionOrchestrator] Failed to start Sing-box")
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
