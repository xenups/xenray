"""Core Health Monitor - Active dual-process health monitoring for Xray-core and Sing-box (TUN mode).

Continuously polls process IDs and execution status during CONNECTED/STARTING states.
Executes cascading teardown, TUN/route/DNS cleanup, FSM error reset, and Toast error on crash.

Thread isolation is CRITICAL: the polling loop executes blocking synchronous calls
(``psutil.pid_exists``, service ``is_running`` checks, PID-file I/O) every second.
It MUST always run on a dedicated background daemon thread, never as an asyncio
task on the running (potentially Flet UI) event loop — a loop scheduled on the UI
event loop starves it and events stop processing.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

from src.core.event_bus import EVENT_CORE_CRASHED, event_bus as default_event_bus
from src.core.fsm.connection_fsm import ConnectionState, connection_fsm as default_fsm
from src.core.logger import logger
from src.utils.process_utils import ProcessUtils


class CoreHealthMonitor:
    """Active health monitor for Xray-core and Sing-box core processes."""

    POLL_INTERVAL = 1.0  # seconds between health polls

    def __init__(
        self,
        xray_service=None,
        singbox_service=None,
        route_manager_service=None,
        dns_configurator=None,
        fsm=None,
        bus=None,
        toast_callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._xray_service = xray_service
        self._singbox_service = singbox_service
        self._route_manager_service = route_manager_service
        self._dns_configurator = dns_configurator
        self._fsm = fsm or default_fsm
        self._bus = bus or default_event_bus
        self._toast_callback = toast_callback

        self._monitor_task: Optional[asyncio.Task] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._is_monitoring = False

    def setup(
        self,
        xray_service=None,
        singbox_service=None,
        route_manager_service=None,
        dns_configurator=None,
        toast_callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """Bind or update service dependencies."""
        if xray_service is not None:
            self._xray_service = xray_service
        if singbox_service is not None:
            self._singbox_service = singbox_service
        if route_manager_service is not None:
            self._route_manager_service = route_manager_service
        if dns_configurator is not None:
            self._dns_configurator = dns_configurator
        if toast_callback is not None:
            self._toast_callback = toast_callback

    def start_monitoring(self) -> None:
        """Start active health monitoring in a dedicated background daemon thread.

        The polling loop runs blocking synchronous process checks (psutil, file
        I/O) every second, so it is ALWAYS isolated onto its own daemon thread.
        It is never scheduled as an asyncio task on the running event loop —
        if the caller happens to be on the Flet UI loop, scheduling the loop
        there would starve the UI (events queue up and stop processing).
        """
        if self._is_monitoring:
            return
        self._is_monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._run_sync_health_loop,
            daemon=True,
            name="CoreHealthMonitor",
        )
        self._monitor_thread.start()
        logger.info("[CoreHealthMonitor] Active process health monitoring thread started.")

    def stop_monitoring(self) -> None:
        """Stop active health monitoring loop.

        ``_is_monitoring`` is flipped so the daemon thread exits on its next
        iteration (within POLL_INTERVAL); it is not joined so teardown is never
        blocked by an in-flight poll.
        """
        self._is_monitoring = False
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            self._monitor_task = None
        logger.info("[CoreHealthMonitor] Active process health monitoring stopped.")

    def _service_is_running(self, service) -> bool:
        """Safely check if service is running regardless of whether is_running is a method, property, or bool."""
        if service is None:
            return False
        attr = getattr(service, "is_running", None)
        if attr is None:
            return False
        if callable(attr):
            try:
                return bool(attr())
            except Exception:
                return False
        return bool(attr)

    def _poll_once(self) -> bool:
        """Perform a single health check tick.

        Returns True when a core process crashed and crash handling has been
        executed (the caller should stop polling), False otherwise.
        """
        current_state = self._fsm.state
        if current_state not in {
            ConnectionState.CONNECTED,
            ConnectionState.STARTING,
            ConnectionState.PREPARING,
        }:
            return False

        # Check Xray-core health
        if self._xray_service:
            xray_pid = getattr(self._xray_service, "pid", None) or getattr(self._xray_service, "_pid", None)
            if xray_pid is not None:
                xray_running = self._service_is_running(self._xray_service)
                if not ProcessUtils.is_running(xray_pid) or not xray_running:
                    logger.error(
                        f"[CoreHealthMonitor] Xray-core process (PID {xray_pid}) crashed or exited unexpectedly!"
                    )
                    self.handle_crash_sync(crashed_engine="xray", pid=xray_pid)
                    return True

        # Check Sing-box (TUN engine) health
        if self._singbox_service:
            singbox_pid = getattr(self._singbox_service, "pid", None) or getattr(self._singbox_service, "_pid", None)
            if singbox_pid is not None:
                singbox_running = self._service_is_running(self._singbox_service)
                if not ProcessUtils.is_running(singbox_pid) or not singbox_running:
                    logger.error(
                        f"[CoreHealthMonitor] Sing-box process (PID {singbox_pid}) crashed or exited unexpectedly!"
                    )
                    self.handle_crash_sync(crashed_engine="singbox", pid=singbox_pid)
                    return True

        return False

    def _run_sync_health_loop(self) -> None:
        """Dedicated background daemon thread polling loop (never the UI event loop)."""
        import time

        while self._is_monitoring:
            try:
                if self._poll_once():
                    break
                time.sleep(self.POLL_INTERVAL)
            except Exception as e:
                logger.error(f"[CoreHealthMonitor] Error in health loop thread: {e}")
                time.sleep(self.POLL_INTERVAL)

    def handle_crash_sync(self, crashed_engine: str, pid: Optional[int]) -> None:
        """Synchronous crash execution helper (thread-safe)."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.handle_crash(crashed_engine, pid))
        except RuntimeError:
            asyncio.run(self.handle_crash(crashed_engine, pid))

    async def _health_loop(self) -> None:
        """Async polling loop variant (API compatibility only).

        ``start_monitoring`` always uses the dedicated daemon thread. Even if
        this coroutine is scheduled on the UI event loop by mistake, every
        blocking process check is offloaded via ``asyncio.to_thread`` so the
        event loop is never blocked.
        """
        while self._is_monitoring:
            try:
                crashed = await asyncio.to_thread(self._poll_once)
                if crashed:
                    break
                await asyncio.sleep(self.POLL_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[CoreHealthMonitor] Error in health loop: {e}")
                await asyncio.sleep(self.POLL_INTERVAL)

    async def handle_crash(self, crashed_engine: str, pid: Optional[int]) -> None:
        """Execute crash detection, cascading teardown, TUN/DNS cleanup, FSM error reset, and Toast."""
        logger.error(f"[CoreHealthMonitor] Handling crash for engine='{crashed_engine}', pid={pid}")
        self._is_monitoring = False

        # 1. Publish EVENT_CORE_CRASHED event over EventBus
        self._bus.publish(
            EVENT_CORE_CRASHED,
            {
                "crashed_engine": crashed_engine,
                "pid": pid,
            },
        )

        # 2. Cascading Teardown: Forcibly kill remaining core process by PID
        if crashed_engine == "singbox":
            if self._xray_service:
                xray_pid = getattr(self._xray_service, "pid", None) or getattr(self._xray_service, "_pid", None)
                if xray_pid:
                    logger.warning(f"[CoreHealthMonitor] Cascading kill of Xray-core PID {xray_pid}")
                    ProcessUtils.kill_process(xray_pid, force=True)
                try:
                    self._xray_service.stop()
                except Exception:
                    pass
        elif crashed_engine == "xray":
            if self._singbox_service:
                sb_pid = getattr(self._singbox_service, "pid", None) or getattr(self._singbox_service, "_pid", None)
                if sb_pid:
                    logger.warning(f"[CoreHealthMonitor] Cascading kill of Sing-box PID {sb_pid}")
                    ProcessUtils.kill_process(sb_pid, force=True)
                try:
                    self._singbox_service.stop()
                except Exception:
                    pass

        # 3. Clean up virtual TUN network adapters, routing tables, and system DNS
        if self._route_manager_service:
            try:
                self._route_manager_service.cleanup_routes()
            except Exception as e:
                logger.error(f"[CoreHealthMonitor] Error cleaning routes: {e}")

        if self._dns_configurator:
            try:
                self._dns_configurator.restore_dns()
            except Exception as e:
                logger.error(f"[CoreHealthMonitor] Error restoring DNS: {e}")

        # 4. Force FSM state to ERROR
        self._fsm.transition_to(
            ConnectionState.ERROR,
            payload={"reason": "core_crashed", "engine": crashed_engine},
            force=True,
        )

        # 5. Trigger Toast Notification
        err_msg = "اتصال به دلیل کرش هسته قطع شد"
        if self._toast_callback:
            try:
                self._toast_callback(err_msg, "error")
            except Exception as e:
                logger.error(f"[CoreHealthMonitor] Toast callback failed: {e}")
