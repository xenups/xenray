"""Connection Orchestrator - Coordinates connection workflow."""

from __future__ import annotations

import time
from typing import Optional

from loguru import logger

from src.core.constants import (
    CORE_SINGBOX,
    CORE_XRAY,
    MODE_PROXY,
    MODE_VPN,
    OUTPUT_CONFIG_PATH,
)
from src.core.i18n import t
from src.services.connection.connection_tester import ConnectionTester
from src.utils.firewall_manager import FirewallManager
from src.utils.log_utils import purge_all_logs_on_connect
from src.utils.network_utils import NetworkUtils

TUN_WARMUP_SECONDS = 0.8
HEALTH_RETRIES = 3
HEALTH_RETRY_DELAY_SECONDS = 0.5


class ConnectionOrchestrator:
    """Orchestrates connection establishment and teardown workflow."""

    ATTEMPT_SKIPPED = "skipped"
    ATTEMPT_ABORTED = "aborted"
    ATTEMPT_FAILED = "failed"
    ATTEMPT_SUCCESS = "success"

    def __init__(
        self,
        app_context,
        network_validator,
        xray_processor,
        xray_service,
        legacy_config_service,
        singbox_service=None,
    ):
        self._app_context = app_context
        self._network_validator = network_validator
        self._xray_processor = xray_processor
        self._xray_service = xray_service
        self._legacy_config_service = legacy_config_service
        self._singbox_service = singbox_service

    def get_core_engine(self) -> str:
        """Return the active core (proxy) engine. Always 'xray' in XenRay architecture."""
        return CORE_XRAY

    def get_tun_engine(self) -> str:
        """Return the selected TUN engine ('xray' or 'singbox') from settings."""
        return self._resolve_tun_engine()

    def _resolve_tun_engine(self) -> str:
        try:
            engine = self._app_context.settings.get_tun_engine()
        except Exception:
            engine = CORE_SINGBOX
        return engine if engine in (CORE_XRAY, CORE_SINGBOX) else CORE_SINGBOX

    def _uses_singbox_tun(self, mode: str) -> bool:
        if mode != MODE_VPN or self._singbox_service is None:
            return False
        return self.get_tun_engine() == CORE_SINGBOX

    def establish_connection(self, file_path: str, mode: str, step_callback=None) -> tuple[bool, Optional[dict]]:
        try:
            purge_all_logs_on_connect()

            original_config = self._load_and_validate_config(file_path, step_callback)
            if not original_config:
                return False, None

            configs_to_try = self._resolve_candidate_configs(original_config)

            if not self._pre_connection_checks(step_callback):
                return False, None

            use_singbox = self._uses_singbox_tun(mode)
            if use_singbox:
                logger.info("[ConnectionOrchestrator] Sing-box TUN engine selected (dual-engine mode)")

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

    def _attempt_single_connection(
        self,
        label: str,
        config: dict,
        mode: str,
        use_singbox: bool,
        file_path: str,
        step_callback,
    ) -> tuple[str, Optional[dict]]:
        if label == "original":
            logger.warning("[ConnectionOrchestrator] Falling back to original legacy configuration")
            if step_callback:
                step_callback(t("connection.falling_back"))

        xray_pid = None
        singbox_pid = None

        try:
            process_mode = MODE_PROXY if use_singbox else mode
            processed_config, socks_port = self._prepare_configuration(config, process_mode, step_callback)
            if not processed_config:
                return self.ATTEMPT_SKIPPED, None

            xray_pid = self._start_xray(step_callback)
            if not xray_pid:
                return self.ATTEMPT_SKIPPED, None

            if use_singbox:
                singbox_pid = self._start_singbox(processed_config, socks_port, step_callback)
                if not singbox_pid:
                    self._xray_service.stop()
                    return self.ATTEMPT_ABORTED, None

            is_tun = mode == MODE_VPN or use_singbox
            if self._verify_connection_health(processed_config, step_callback, socks_port, warm_up=is_tun):
                self._ensure_lan_firewall_rule(socks_port)
                connection_info = self._finalize_connection(file_path, mode, xray_pid, singbox_pid, step_callback)
                return self.ATTEMPT_SUCCESS, connection_info

            logger.error(f"[ConnectionOrchestrator] {label.capitalize()} config failed health check")
            self.teardown_connection({"xray_pid": xray_pid, "singbox_pid": singbox_pid})
            return self.ATTEMPT_FAILED, None

        except Exception:
            logger.warning(f"[ConnectionOrchestrator] Cleaning up resources after failed attempt ({label})")
            self._safe_teardown({"xray_pid": xray_pid, "singbox_pid": singbox_pid})
            raise

    def _resolve_candidate_configs(self, original_config: dict) -> list:
        is_legacy = self._legacy_config_service.is_legacy(original_config)

        if is_legacy:
            logger.info("[ConnectionOrchestrator] Legacy config detected, preparing migration")
            migrated_config = self._legacy_config_service.migrate_config(original_config)
            return [("migrated", migrated_config), ("original", original_config)]

        return [("standard", original_config)]

    def teardown_connection(self, connection_info: dict):
        if self._singbox_service is not None:
            self._singbox_service.stop()
        self._xray_service.stop()

        self._remove_lan_firewall_rule()
        logger.info("Connection torn down successfully")

    def _ensure_lan_firewall_rule(self, socks_port: int) -> None:
        settings = getattr(self._app_context, "settings", None)
        if not settings or not hasattr(settings, "get_allow_lan"):
            return
        try:
            if not settings.get_allow_lan() or not socks_port:
                return
            http_port = getattr(settings, "get_http_port", lambda: None)()
            if not isinstance(http_port, int):
                http_port = None
            FirewallManager.allow_lan_sharing_ports(socks_port, http_port=http_port)
        except Exception as e:
            logger.warning(f"[ConnectionOrchestrator] Failed to apply LAN firewall rule: {e}")

    @staticmethod
    def _remove_lan_firewall_rule() -> None:
        try:
            FirewallManager.remove_lan_firewall_rule()
        except Exception as e:
            logger.warning(f"[ConnectionOrchestrator] Failed to remove LAN firewall rule: {e}")

    def _safe_teardown(self, connection_info: dict):
        try:
            self.teardown_connection(connection_info)
        except Exception as e:
            logger.error(f"[ConnectionOrchestrator] Teardown after failed attempt raised: {e}")

    def _verify_connection_health(
        self,
        config: dict,
        step_callback,
        health_socks_port: int = 0,
        warm_up: bool = False,
    ) -> bool:
        if step_callback:
            step_callback(t("connection.verifying_latency"))

        if warm_up:
            logger.info(f"[ConnectionOrchestrator] TUN warm-up ({TUN_WARMUP_SECONDS}s)...")
            time.sleep(TUN_WARMUP_SECONDS)

        socks_port = health_socks_port if health_socks_port > 0 else 0
        if socks_port:
            logger.debug(
                f"[ConnectionOrchestrator] Routing health check through existing SOCKS proxy port {socks_port}"
            )

        last_latency = None
        for attempt in range(1, HEALTH_RETRIES + 1):
            success, latency, _ = ConnectionTester.test_connection_sync(config, socks_port=socks_port)
            if success:
                logger.info(f"[ConnectionOrchestrator] Connection verified (attempt {attempt}): {latency}")
                return True
            last_latency = latency
            logger.warning(
                f"[ConnectionOrchestrator] Verification attempt {attempt}/{HEALTH_RETRIES} failed: {latency}"
            )
            if attempt < HEALTH_RETRIES:
                time.sleep(HEALTH_RETRY_DELAY_SECONDS)

        logger.warning(
            f"[ConnectionOrchestrator] Connection verification failed after {HEALTH_RETRIES} attempts: {last_latency}"
        )
        if step_callback:
            step_callback(t("connection.failed"))
        return False

    def _pre_connection_checks(self, step_callback) -> bool:
        if step_callback:
            step_callback(t("connection.checking_network"))

        if not self._network_validator.check_internet_connection():
            logger.error("No internet connection detected")
            if step_callback:
                step_callback(t("connection.no_internet"))
            return False

        return True

    def _load_and_validate_config(self, file_path: str, step_callback) -> Optional[dict]:
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

    def _prepare_configuration(self, config: dict, mode: str, step_callback) -> tuple[Optional[dict], Optional[int]]:
        if step_callback:
            step_callback(t("connection.processing_config"))

        processed_config = self._xray_processor.process_config(config, mode=mode)
        socks_port = self._xray_processor.get_socks_port(processed_config)

        if not self._xray_processor.save_config(processed_config, OUTPUT_CONFIG_PATH):
            return None, None

        return processed_config, socks_port

    def _start_xray(self, step_callback) -> Optional[int]:
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
        if step_callback:
            step_callback(t("connection.initializing_vpn"))

        is_quic = self._xray_processor.is_quic_transport(processed_config)
        mtu_mode = "quic_safe" if is_quic else "auto"
        optimal_mtu = NetworkUtils.detect_optimal_mtu(mtu_mode=mtu_mode)
        logger.info(f"[ConnectionOrchestrator] Using MTU for TUN interface: {optimal_mtu}")

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
        if step_callback:
            step_callback(t("connection.finalizing"))

        import time as _time

        connection_info = {
            "mode": mode,
            "xray_pid": xray_pid,
            "singbox_pid": singbox_pid,
            "file": file_path,
            "connected_at": _time.time(),
        }

        logger.info(f"Successfully connected in {mode} mode")
        return connection_info


__all__ = ["ConnectionOrchestrator"]
