"""Sing-box Service Manager (Lean Process Lifecycle Controller)."""
from __future__ import annotations

import asyncio
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
from src.core.constants import SINGBOX_CONFIG_PATH, SINGBOX_EXECUTABLE, SINGBOX_LOG_FILE, SINGBOX_PID_FILE
from src.core.logger import logger
from src.services.route_manager_service import RouteManagerService
from src.utils.network_interface import NetworkInterfaceDetector
from src.utils.platform_utils import PlatformUtils
from src.utils.process_utils import ProcessUtils

XRAY_READY_RETRY_COUNT = 20
XRAY_READY_RETRY_DELAY = 0.5
PROCESS_TERMINATE_TIMEOUT = 8.0
SINGBOX_CHECK_TIMEOUT = 15.0
LOOP_START_TIMEOUT = 2.0


class SingboxService:
    """Manages the sing-box TUN process lifecycle."""

    def __init__(self) -> None:
        self._process: Optional[asyncio.subprocess.Process] = None
        self._pid: Optional[int] = None
        self._log_handle = None
        self._cleanup_lock = threading.RLock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

        self._config_builder = SingboxConfigBuilder()
        self._route_manager = RouteManagerService()
        self._smhr_was_enabled: Optional[bool] = None

        self._check_and_restore_pid()
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

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop

        def _run_loop():
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self._loop_thread = threading.Thread(target=_run_loop, daemon=True, name="singbox-asyncio")
        self._loop_thread.start()

        deadline = time.monotonic() + LOOP_START_TIMEOUT
        while self._loop is None:
            if time.monotonic() > deadline:
                raise RuntimeError("[SingboxService] asyncio loop failed to start")
            time.sleep(0.01)
        return self._loop

    def _run_async(self, coro, timeout: float = 60.0):
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    async def _run_check(self):
        proc = await asyncio.subprocess.create_subprocess_exec(
            SINGBOX_EXECUTABLE,
            "check",
            "-c",
            SINGBOX_CONFIG_PATH,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=PlatformUtils.get_subprocess_flags(),
            startupinfo=PlatformUtils.get_startupinfo(),
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout, stderr

    async def _spawn_process(self) -> Optional[asyncio.subprocess.Process]:
        return await asyncio.subprocess.create_subprocess_exec(
            SINGBOX_EXECUTABLE,
            "run",
            "-c",
            SINGBOX_CONFIG_PATH,
            stdout=self._log_handle,
            stderr=self._log_handle,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            startupinfo=PlatformUtils.get_startupinfo(),
        )

    async def _terminate_process(self) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            return
        try:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=PROCESS_TERMINATE_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning("[SingboxService] Graceful terminate timed out, forcing kill")
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
        except Exception as e:
            logger.error(f"[SingboxService] Error terminating process: {e}")
            try:
                ProcessUtils.kill_process(process.pid, force=True)
            except Exception:
                pass

    @staticmethod
    def _terminate_pid(pid: int) -> None:
        if not pid or not ProcessUtils.is_running(pid):
            return
        try:
            ProcessUtils.kill_process(pid, force=False)
            deadline = time.monotonic() + PROCESS_TERMINATE_TIMEOUT
            while ProcessUtils.is_running(pid) and time.monotonic() < deadline:
                time.sleep(0.1)
            if ProcessUtils.is_running(pid):
                logger.warning("[SingboxService] Graceful stop timed out, forcing kill")
                ProcessUtils.kill_process(pid, force=True)
        except Exception as e:
            logger.error(f"[SingboxService] Error stopping PID {pid}: {e}")

    def _check_and_restore_pid(self) -> None:
        if os.path.exists(SINGBOX_PID_FILE):
            try:
                with open(SINGBOX_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    self._pid = old_pid
                    logger.debug(f"[SingboxService] Restored PID {self._pid} from file")
            except Exception:
                pass

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
    ) -> Optional[int]:
        try:
            iface_name, _, _, gateway = NetworkInterfaceDetector.get_primary_interface()
            self._route_manager.setup_routes(proxy_server_ip, gateway, allow_lan=allow_lan)
            self._smhr_was_enabled = PlatformUtils.suppress_smhr()

            config = self._config_builder.build(
                xray_socks_port, proxy_server_ip, routing_country, iface_name, routing_rules, mtu
            )

            if not self._wait_for_xray_ready(xray_socks_port) or not self._write_config_and_start(config):
                self._route_manager.cleanup_routes()
                PlatformUtils.restore_smhr(self._smhr_was_enabled)
                return None

            self._pid = self._process.pid
            try:
                with open(SINGBOX_PID_FILE, "w") as f:
                    f.write(str(self._pid))
            except Exception as e:
                logger.error(f"[SingboxService] Failed to write PID file: {e}")

            logger.info(f"[SingboxService] sing-box started successfully | PID: {self._pid}")
            return self._pid
        except Exception as e:
            logger.exception(f"[SingboxService] Failed to start: {e}")
            self._close_log()
            self._route_manager.cleanup_routes()
            PlatformUtils.restore_smhr(self._smhr_was_enabled)
            return None

    def _wait_for_xray_ready(self, port: int) -> bool:
        logger.info(f"[SingboxService] Waiting for Xray on port {port}...")
        for _ in range(XRAY_READY_RETRY_COUNT):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    logger.info("[SingboxService] Xray is ready.")
                    return True
            except (socket.timeout, TimeoutError, ConnectionRefusedError, OSError):
                time.sleep(XRAY_READY_RETRY_DELAY)
        logger.error("[SingboxService] Timed out waiting for Xray.")
        return False

    def _write_config_and_start(self, config: dict) -> bool:
        try:
            with open(SINGBOX_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            from src.utils.process_utils import rotate_oversized_log_file

            rotate_oversized_log_file(SINGBOX_LOG_FILE)
            self._log_handle = open(SINGBOX_LOG_FILE, "w", encoding="utf-8")
            try:
                if not self._validate_config():
                    return False
                self._process = self._run_async(self._spawn_process(), timeout=30)
                return self._process is not None
            except Exception:
                self._close_log()
                raise
        except Exception as e:
            logger.error(f"[SingboxService] Failed to start process: {e}")
            self._close_log()
            return False

    def _validate_config(self) -> bool:
        try:
            rc, stdout, stderr = self._run_async(self._run_check(), timeout=SINGBOX_CHECK_TIMEOUT)
            if rc != 0:
                err = (stdout or stderr).decode(errors="replace").strip()
                logger.error(f"[SingboxService] Config validation failed (rc={rc}): {err}")
                return False
            return True
        except Exception as e:
            logger.error(f"[SingboxService] Config validation error: {e}")
            return False

    def _close_log(self) -> None:
        if self._log_handle:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None

    def stop(self) -> None:
        with self._cleanup_lock:
            pid_to_kill = self._pid or (self._process.pid if self._process else None)
            try:
                if self._process is not None:
                    self._run_async(self._terminate_process(), timeout=PROCESS_TERMINATE_TIMEOUT + 5)
                elif pid_to_kill:
                    self._terminate_pid(pid_to_kill)
            except Exception as e:
                logger.warning(f"[SingboxService] Async termination failed: {e}")
                if pid_to_kill:
                    self._terminate_pid(pid_to_kill)

            self._process = None
            self._pid = None
            if os.path.exists(SINGBOX_PID_FILE):
                try:
                    os.remove(SINGBOX_PID_FILE)
                except Exception:
                    pass

            self._route_manager.cleanup_routes()
            self._close_log()
            PlatformUtils.restore_smhr(self._smhr_was_enabled)
            self._smhr_was_enabled = None
            logger.info("[SingboxService] Stopped.")

    def is_running(self) -> bool:
        if self._pid and ProcessUtils.is_running(self._pid):
            return True
        if os.path.exists(SINGBOX_PID_FILE):
            try:
                with open(SINGBOX_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    self._pid = old_pid
                    return True
            except Exception:
                pass
        self._pid = None
        self._process = None
        return False

    @property
    def pid(self) -> Optional[int]:
        return self._pid

    def get_version(self) -> Optional[str]:
        if not os.path.exists(SINGBOX_EXECUTABLE):
            return None
        try:
            res = subprocess.run(
                [SINGBOX_EXECUTABLE, "version"],
                capture_output=True,
                text=True,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            if res.returncode == 0:
                parts = res.stdout.split("\n")[0].split()
                if len(parts) >= 3:
                    return parts[2]
            return None
        except Exception:
            return None
