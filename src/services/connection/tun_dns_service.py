"""TunDnsService - facade over the platform TUN-DNS adapter.

SRP: the actual NRPT / netsh commands live in the platform layer
(``ITunDnsConfigurator`` → ``WindowsTunDnsConfigurator``), and SMHR lives in
``ISystemSettingsAdapter``. This class keeps the small orchestration + state
(``_smhr_was_enabled``, ``_is_tun_mode``) and delegates the OS side-effects to
the platform factory — so business logic never contains raw OS commands.
"""

from __future__ import annotations

import threading
from typing import Optional

from src.platform.constants import TUN_ADAPTER_NAME
from src.platform.factory import get_system_settings_adapter, get_tun_dns_configurator

# TUN adapter appear wait (30 s total) — kept here for the facade contract.
TUN_ADAPTER_WAIT_ITERATIONS = 60
TUN_ADAPTER_POLL_INTERVAL = 0.5


class TunDnsService:
    """Owns NRPT rules, TUN-adapter DNS, and SMHR state via the OS abstraction."""

    def __init__(self) -> None:
        self._tun_dns = get_tun_dns_configurator()
        self._settings = get_system_settings_adapter()
        self._smhr_was_enabled: Optional[bool] = None
        self._is_tun_mode: bool = False
        self._lock = threading.Lock()

    # -- public API ----------------------------------------------------
    def setup_tun_dns(self, config_file_path: str) -> bool:
        """Configure DNS + NRPT for the virtual TUN adapter if the config is a
        TUN profile. Returns True on success / non-TUN no-op; False on failure."""
        self._smhr_was_enabled = self._settings.suppress_smhr()
        ok = self._tun_dns.configure_tun_dns(config_file_path, TUN_ADAPTER_NAME)
        self._is_tun_mode = ok
        return ok

    def cleanup(self) -> None:
        with self._lock:
            self._tun_dns.cleanup_tun_dns(TUN_ADAPTER_NAME)
            self._settings.restore_smhr(self._smhr_was_enabled)
            self._smhr_was_enabled = None
            self._is_tun_mode = False

    # -- backward-compat thin proxies (delegate to the adapters) --------
    def _remove_nrpt_rules(self) -> None:
        self._tun_dns.cleanup_tun_dns(TUN_ADAPTER_NAME)

    def _cleanup_tun_dns(self) -> None:
        self._tun_dns.cleanup_tun_dns(TUN_ADAPTER_NAME)

    def _suppress_smhr(self) -> None:
        self._smhr_was_enabled = self._settings.suppress_smhr()

    def _restore_smhr(self) -> None:
        self._settings.restore_smhr(self._smhr_was_enabled)
        self._smhr_was_enabled = None

    @staticmethod
    def read_smhr_state() -> Optional[bool]:
        return get_system_settings_adapter().read_smhr_state()

    @staticmethod
    def set_smhr_state(enabled: bool) -> None:
        get_system_settings_adapter().set_smhr_state(enabled)
