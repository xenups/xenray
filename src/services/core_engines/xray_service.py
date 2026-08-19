"""XrayService - facade/orchestrator for the Xray core.

SRP decomposition:
    * OS process lifecycle        → :class:`XrayProcessManager`
    * Windows TUN DNS / NRPT / SMHR → :class:`TunDnsService`
    * log observation             → :class:`XrayLogWatcher`
    * SNI-spoof helper            → SniSpoofService (shared)

This class stays a thin facade composing them. No PowerShell/netsh/subprocess
network commands live here anymore. Public signatures are stable.
"""

from __future__ import annotations

import atexit
import os
import signal
import threading
import time
from typing import Optional

from src.core.constants import XRAY_LOCATION_ASSET, XRAY_LOG_FILE
from src.core.event_bus import EVENT_CORE_PROCESS_STOPPED, event_bus
from src.core.logger import logger
from src.services.connection.tun_dns_service import TunDnsService
from src.services.core_engines.xray_process_manager import XrayProcessManager

# Constants
PROCESS_START_DELAY = 0.2  # seconds - delay to ensure previous instance is terminated


class XrayService:
    """Facade orchestrating the Xray core: process + Windows network + SNI helper."""

    def __init__(self):
        """Initialize Xray service."""
        self._process_mgr = XrayProcessManager()
        self._dns_mgr = TunDnsService()
        self._cleanup_lock = threading.Lock()
        self._sni_spoof_service = None  # SniSpoofService, started alongside Xray when enabled
        self._process_mgr.adopt_pid_file()

        # Guarantee teardown even on unclean exit (SIGKILL bypasses this, but
        # SIGTERM, interpreter shutdown, and atexit are all covered).
        atexit.register(self._guaranteed_cleanup)
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
        except (OSError, ValueError):
            pass

        if hasattr(signal, "SIGBREAK"):
            try:
                signal.signal(signal.SIGBREAK, self._signal_handler)  # type: ignore[attr-defined]
            except (OSError, ValueError, AttributeError):
                pass

    # ------------------------------------------------------------------
    # Signal / atexit handlers
    # ------------------------------------------------------------------

    def _signal_handler(self, signum, frame):
        """Handle OS termination signals by performing a clean stop."""
        logger.info(f"[XrayService] Received signal {signum}, performing cleanup...")
        self._guaranteed_cleanup()

    def _guaranteed_cleanup(self):
        """Idempotent teardown — safe to call multiple times (guarded by lock).

        Single source of truth for process + PID-file + SNI-helper + Windows
        network teardown.
        """
        with self._cleanup_lock:
            try:
                self._stop_sni_spoof_helper()
            except Exception as e:
                logger.warning(f"[XrayService] SNI helper cleanup error in guaranteed teardown: {e}")
            self._process_mgr.kill_and_cleanup()
            try:
                self._dns_mgr.cleanup()
            except Exception as e:
                logger.warning(f"[XrayService] DNS cleanup error in guaranteed teardown: {e}")

    # ------------------------------------------------------------------
    # Delegated Windows-network helpers (backward-compat thin proxies)
    # ------------------------------------------------------------------
    # Kept so existing callers/tests that reach into these names still work;
    # the real logic lives in TunDnsService.

    def _remove_nrpt_rules(self):
        self._dns_mgr._remove_nrpt_rules()

    def _cleanup_tun_dns(self):
        self._dns_mgr._cleanup_tun_dns()

    @staticmethod
    def _read_smhr_state() -> Optional[bool]:
        return TunDnsService.read_smhr_state()

    @staticmethod
    def _set_smhr_state(enabled: bool):
        TunDnsService.set_smhr_state(enabled)

    def _suppress_smhr(self):
        self._dns_mgr._suppress_smhr()

    def _restore_smhr(self):
        self._dns_mgr._restore_smhr()

    @staticmethod
    def _check_ipv6_interface_available(creation_flags: int) -> bool:
        return TunDnsService.ipv6_available(creation_flags)

    def _configure_windows_tun_dns(self, config_file_path: str):
        self._dns_mgr.setup_tun_dns(config_file_path)

    # ------------------------------------------------------------------
    # Instance management
    # ------------------------------------------------------------------

    def _check_and_restore_pid(self):
        self._process_mgr.adopt_pid_file()

    def _cleanup_previous_instance(self):
        """Kill any previous instance and clean Windows network state."""
        self._process_mgr.cleanup_previous_instance()

        # Always remove NRPT rules, clear TUN DNS, and restore SMHR from any
        # previous crashed session before starting a new one.
        try:
            self._dns_mgr.cleanup()
        except Exception as e:
            logger.warning(f"[XrayService] pre-start network cleanup failed: {e}")

    def _start_sni_spoof_helper(self):
        """Start the SNI-spoof helper service when enabled (fail-soft).

        Uses the shared SniSpoofService instance so a UI toggle and a connection
        drive the SAME listener (the lifecycle bridge owns the toggle side).
        """
        try:
            from src.repositories.settings_repository import SettingsRepository
            from src.services.sni_spoof.sni_spoof_service import get_sni_spoof_service

            repo = SettingsRepository()
            if not repo.get_sni_spoof_enabled():
                return
            service = get_sni_spoof_service(settings_repo=repo)
            self._sni_spoof_service = service
            if not service.running:
                service.start()
        except Exception as e:
            logger.warning(f"[XrayService] SNI spoof helper start failed (fail-soft): {e}")

    def _stop_sni_spoof_helper(self):
        """Stop the SNI-spoof helper service (called on Xray teardown)."""
        try:
            from src.services.sni_spoof.sni_spoof_service import get_sni_spoof_service

            service = self._sni_spoof_service or get_sni_spoof_service()
            self._sni_spoof_service = service
            service.stop()
        except Exception as e:
            logger.warning(f"[XrayService] SNI spoof helper stop error: {e}")

    def start(self, config_file_path: str) -> Optional[int]:
        """Start Xray with the given configuration."""
        # Ensure cleanup again just in case
        self._cleanup_previous_instance()

        logger.debug(f"[XrayService] Starting Xray with config: {config_file_path}")

        if not os.path.isfile(config_file_path):
            logger.error(f"[XrayService] Config not found: {config_file_path}")
            return None

        # Ensure XRAY_LOCATION_ASSET environment variable is set
        os.environ["XRAY_LOCATION_ASSET"] = XRAY_LOCATION_ASSET
        logger.debug(f"[XrayService] XRAY_LOCATION_ASSET set to: {XRAY_LOCATION_ASSET}")

        # Small delay to ensure previous instance is fully terminated
        time.sleep(PROCESS_START_DELAY)

        # Delegate process launch to the process manager.
        pid = self._process_mgr.start(config_file_path, XRAY_LOG_FILE)
        if pid is None:
            return None

        # SNI Spoof: start the helper alongside Xray when enabled.
        # Fail-soft: non-admin / missing pydivert -> SniSpoofService.start
        # returns False + logs, never raises or blocks Xray startup.
        self._start_sni_spoof_helper()

        # Windows virtual adapter DNS override — delegate to the DNS manager,
        # run in a daemon thread so we never block the UI thread.
        dns_thread = threading.Thread(
            target=self._dns_mgr.setup_tun_dns,
            args=(config_file_path,),
            daemon=True,
            name="xenray-tun-dns",
        )
        dns_thread.start()

        return pid

    def stop(self) -> bool:
        """Stop Xray process."""
        # Perform guaranteed teardown (process, network DNS/NRPT/SMHR, SNI helper)
        self._guaranteed_cleanup()

        # Stop the SNI-spoof helper alongside Xray
        self._stop_sni_spoof_helper()

        # Kill the process (memory PID then PID file) and remove the PID file
        pid_to_kill = self._process_mgr.kill_and_cleanup()

        if pid_to_kill is None:
            logger.debug("[XrayService] No process to stop")
            return True

        try:
            event_bus.publish(EVENT_CORE_PROCESS_STOPPED, {"engine": "xray", "pid": pid_to_kill})
            return True
        except Exception as e:
            logger.error(f"[XrayService] Failed to stop Xray: {e}")
            return False

    @property
    def pid(self) -> Optional[int]:
        """Get process PID if running."""
        return self._process_mgr.pid

    @property
    def is_running(self) -> bool:
        """Check if Xray is currently running."""
        return self._process_mgr.is_running
