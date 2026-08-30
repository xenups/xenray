"""Sing-box Service Manager (SRP facade/orchestrator).

The asyncio + subprocess lifecycle now lives in :class:`SingboxProcessManager`;
config building and routing already live in ``SingboxConfigBuilder`` and
``RouteManagerService``. This class remains a thin facade that composes them
with the top-level Windows network orchestration (routes, SMHR) and keeps the
public API stable (``start``/``stop``/``is_running``/``pid``/``get_version`` and
the backward-compat config-delegate helpers).
"""
from __future__ import annotations

import atexit
import json
import os
import signal
import socket
import subprocess
import threading
import time
from typing import List, Optional, Union

from src.core.config_builders.singbox_config_builder import SingboxConfigBuilder
from src.core.constants import SINGBOX_CONFIG_PATH, SINGBOX_EXECUTABLE, SINGBOX_LOG_FILE
from src.core.event_bus import EVENT_CORE_PROCESS_STOPPED, event_bus
from src.core.logger import logger
from src.platform.factory import get_network_adapter, get_process_adapter, get_system_settings_adapter
from src.services.connection.route_manager_service import RouteManagerService
from src.services.core_engines.singbox_process_manager import SingboxProcessManager

XRAY_READY_RETRY_COUNT = 20
XRAY_READY_RETRY_DELAY = 0.5


class SingboxService:
    """Manages the sing-box TUN process lifecycle (facade)."""

    def __init__(self) -> None:
        self._proc = SingboxProcessManager()
        self._cleanup_lock = threading.RLock()

        self._config_builder = SingboxConfigBuilder()
        self._route_manager = RouteManagerService()
        self._smhr_was_enabled: Optional[bool] = None

        self._proc.adopt_pid_file()
        atexit.register(self._guaranteed_cleanup)

        for sig in (signal.SIGTERM,):
            try:
                prev = signal.getsignal(sig)
                if callable(prev) and prev not in (signal.SIG_DFL, signal.SIG_IGN):

                    def _chained(signum, frame, _prev=prev):
                        self._signal_handler(signum, frame)
                        _prev(signum, frame)

                    signal.signal(sig, _chained)
                else:
                    signal.signal(sig, self._signal_handler)
            except (OSError, ValueError):
                pass
        try:
            signal.signal(signal.SIGBREAK, self._signal_handler)
        except (OSError, ValueError, AttributeError):
            pass

    def _signal_handler(self, signum, frame) -> None:
        logger.info(f"[SingboxService] Received signal {signum}, performing cleanup...")
        self._guaranteed_cleanup()

    def _guaranteed_cleanup(self) -> None:
        self.stop()

    # Delegates for backward-compatibility with existing tests
    def _normalize_list(self, val):
        return self._config_builder.normalize_list(val)

    def _filter_real_ips(self, lst):
        return self._config_builder.filter_real_ips(lst)

    def _filter_domains(self, lst):
        return self._config_builder.filter_domains(lst)

    def _generate_config(self, *a, **kw):
        return self._config_builder.build(*a, **kw)

    def _is_private_or_reserved(self, ip):
        return RouteManagerService.is_private_or_reserved(ip)

    def _resolve_ips(self, eps):
        return self._route_manager.resolve_ips(eps)

    def _add_static_route(self, ip, gw):
        self._route_manager.add_static_route(ip, gw)

    def _cleanup_routes(self):
        self._route_manager.cleanup_routes()

    def _add_lan_routes(self, gw):
        self._route_manager.add_lan_routes(gw)

    def _cleanup_lan_routes(self):
        self._route_manager._cleanup_lan_routes()

    @property
    def _added_routes(self):
        return self._route_manager._added_routes

    @property
    def _added_lan_routes(self):
        return self._route_manager._added_lan_routes

    def start(
        self,
        xray_socks_port: int,
        proxy_server_ip: Union[str, List[str]] = "",
        routing_country: str = "",
        routing_rules: dict = None,
        mtu: int = 1420,
        allow_lan: bool = False,
        routing_toggles: dict = None,
    ) -> Optional[int]:
        try:
            adapter = get_network_adapter()
            iface_name, _, _, gateway = adapter.get_primary_interface()
            self._route_manager.setup_routes(proxy_server_ip, gateway, allow_lan=allow_lan)
            self._smhr_was_enabled = get_system_settings_adapter().suppress_smhr()

            # Resolve external values to pass as pure inputs to builder
            dns_servers = adapter.get_system_dns_servers()
            local_dns = dns_servers[0] if dns_servers else None

            sni_connect_ip = None
            try:
                from src.core.constants import CONFIG_DIR
                from src.repositories.settings_repository import SettingsRepository

                settings = SettingsRepository(CONFIG_DIR)
                if settings.get_sni_spoof_enabled():
                    sni_connect_ip = settings.get_sni_connect_ip()
            except Exception:
                pass

            config = self._config_builder.build(
                socks_port=xray_socks_port,
                proxy_server_ip=proxy_server_ip,
                # Pass interface_name=None so sing-box relies on dynamic auto_detect_interface: true
                # and keeps outbound direct cleanly interface-agnostic (no static pinning).
                interface_name=None,
                routing_rules=routing_rules,
                mtu=mtu,
                local_dns_server=local_dns,
                sni_connect_ip=sni_connect_ip,
                toggles=routing_toggles,
            )

            self._pre_launch_cleanup()

            if not self._wait_for_xray_ready(xray_socks_port) or not self._write_config_and_start(config):
                self._route_manager.cleanup_routes()
                get_system_settings_adapter().restore_smhr(self._smhr_was_enabled)
                return None

            pid = self._proc.pid
            if pid:
                self._proc.write_pid_file(pid)

            logger.info(f"[SingboxService] sing-box started successfully | PID: {pid}")
            return pid
        except Exception as e:
            logger.exception(f"[SingboxService] Failed to start: {e}")
            self._proc.close_log()
            self._route_manager.cleanup_routes()
            get_system_settings_adapter().restore_smhr(self._smhr_was_enabled)
            return None

    def _pre_launch_cleanup(self) -> None:
        """Ensure orphaned sing-box instances are terminated before launching a new process."""
        try:
            from src.utils.process_utils import ProcessUtils
            ProcessUtils.cleanup_orphaned_core(SINGBOX_EXECUTABLE, exclude_pid=self._proc.pid)
        except Exception as e:
            logger.warning(f"[SingboxService] Pre-launch cleanup warning: {e}")

    def _wait_for_xray_ready(self, port: int) -> bool:
        logger.info(f"[SingboxService] Waiting for Xray SOCKS5 engine on port {port}...")
        for attempt in range(1, XRAY_READY_RETRY_COUNT + 1):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2) as s:
                    s.sendall(b"\x05\x01\x00")
                    s.settimeout(0.2)
                    resp = s.recv(2)
                    if len(resp) >= 2 and resp[0] == 0x05 and resp[1] == 0x00:
                        logger.info(f"[SingboxService] Xray SOCKS5 is ready on port {port} (attempt {attempt}).")
                        return True
            except (socket.timeout, TimeoutError, ConnectionRefusedError, OSError):
                time.sleep(XRAY_READY_RETRY_DELAY)
        logger.error(f"[SingboxService] Timed out waiting for Xray on port {port}.")
        return False

    def _write_config_and_start(self, config: dict) -> bool:
        try:
            with open(SINGBOX_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            self._proc.open_log(SINGBOX_LOG_FILE)
            try:
                if not self._proc.validate_config(SINGBOX_CONFIG_PATH):
                    return False
                process = self._proc.spawn(SINGBOX_CONFIG_PATH)
                return process is not None
            except Exception:
                self._proc.close_log()
                raise
        except Exception as e:
            logger.error(f"[SingboxService] Failed to start process: {e}")
            self._proc.close_log()
            return False

    def stop(self) -> None:
        with self._cleanup_lock:
            pid_to_kill = self._proc.stop()
            self._route_manager.cleanup_routes()
            get_system_settings_adapter().restore_smhr(self._smhr_was_enabled)
            self._smhr_was_enabled = None
            logger.info("[SingboxService] Stopped.")
            event_bus.publish(EVENT_CORE_PROCESS_STOPPED, {"engine": "singbox", "pid": pid_to_kill})

    def is_running(self) -> bool:
        return self._proc.is_running()

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid

    @property
    def exit_code(self) -> Optional[int]:
        return self._proc.get_exit_code()

    def get_last_logs(self, lines: int = 25) -> str:
        return self._proc.get_last_logs(lines=lines)

    def get_version(self) -> Optional[str]:
        if not os.path.exists(SINGBOX_EXECUTABLE):
            return None
        try:
            res = subprocess.run(
                [SINGBOX_EXECUTABLE, "version"],
                capture_output=True,
                text=True,
                creationflags=get_process_adapter().get_subprocess_flags(),
                startupinfo=get_process_adapter().get_startupinfo(),
            )
            if res.returncode == 0:
                parts = res.stdout.split("\n")[0].split()
                if len(parts) >= 3:
                    return parts[2]
            return None
        except Exception:
            return None
