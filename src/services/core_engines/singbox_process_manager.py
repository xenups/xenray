"""SingboxProcessManager - asyncio process lifecycle for the sing-box core.

Single responsibility: own the asyncio event-loop bridge and the sing-box
subprocess (spawn, terminate, log handle, PID). No config building, no routing,
no SMHR — the facade (``SingboxService``) composes this with the network bits.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import threading
import time
from typing import Optional

from src.core.constants import SINGBOX_EXECUTABLE, SINGBOX_PID_FILE
from src.core.logger import logger
from src.platform.factory import get_process_adapter
from src.utils.process_utils import ProcessUtils

# Tuning constants (moved here from the facade — values unchanged).
XRAY_READY_RETRY_COUNT = 20
XRAY_READY_RETRY_DELAY = 0.5
PROCESS_TERMINATE_TIMEOUT = 1.0
SINGBOX_CHECK_TIMEOUT = 15.0
LOOP_START_TIMEOUT = 2.0


class SingboxProcessManager:
    """Owns the sing-box subprocess and its asyncio loop bridge."""

    def __init__(self) -> None:
        self._process: Optional[asyncio.subprocess.Process] = None
        self._pid: Optional[int] = None
        self._log_handle = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

    # -- event-loop bridge ---------------------------------------------
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
                raise RuntimeError("[SingboxProcessManager] asyncio loop failed to start")
            time.sleep(0.01)
        return self._loop

    def run_async(self, coro, timeout: float = 60.0):
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    # -- spawn / check -------------------------------------------------
    async def _run_check(self, config_path: str) -> tuple:
        proc = await asyncio.subprocess.create_subprocess_exec(
            SINGBOX_EXECUTABLE,
            "check",
            "-c",
            config_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=get_process_adapter().get_subprocess_flags(),
            startupinfo=get_process_adapter().get_startupinfo(),
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout, stderr

    async def _spawn_process(self, config_path: str) -> Optional[asyncio.subprocess.Process]:
        return await asyncio.subprocess.create_subprocess_exec(
            SINGBOX_EXECUTABLE,
            "run",
            "-c",
            config_path,
            stdout=self._log_handle,
            stderr=self._log_handle,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            startupinfo=get_process_adapter().get_startupinfo(),
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
                logger.warning("[SingboxProcessManager] Graceful terminate timed out, forcing kill")
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
        except Exception as e:
            logger.error(f"[SingboxProcessManager] Error terminating process: {e}")
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
                logger.warning("[SingboxProcessManager] Graceful stop timed out, forcing kill")
                ProcessUtils.kill_process(pid, force=True)
        except Exception as e:
            logger.error(f"[SingboxProcessManager] Error stopping PID {pid}: {e}")

    # -- log handle ----------------------------------------------------
    def open_log(self, log_file: str) -> None:
        from src.utils.process_utils import rotate_oversized_log_file

        rotate_oversized_log_file(log_file)
        self._log_handle = open(log_file, "w", encoding="utf-8")

    def close_log(self) -> None:
        if self._log_handle:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None

    # -- launch --------------------------------------------------------
    def validate_config(self, config_path: str) -> bool:
        try:
            rc, stdout, stderr = self.run_async(self._run_check(config_path), timeout=SINGBOX_CHECK_TIMEOUT)
            if rc != 0:
                err = (stdout or stderr).decode(errors="replace").strip()
                logger.error(f"[SingboxProcessManager] Config validation failed (rc={rc}): {err}")
                return False
            return True
        except Exception as e:
            logger.error(f"[SingboxProcessManager] Config validation error: {e}")
            return False

    def spawn(self, config_path: str) -> Optional[asyncio.subprocess.Process]:
        self._process = self.run_async(self._spawn_process(config_path), timeout=30)
        if self._process is not None:
            self._pid = self._process.pid
        return self._process

    # -- PID / status --------------------------------------------------
    @property
    def pid(self) -> Optional[int]:
        return self._pid

    def adopt_pid_file(self) -> None:
        if os.path.exists(SINGBOX_PID_FILE):
            try:
                with open(SINGBOX_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    self._pid = old_pid
                    logger.debug(f"[SingboxProcessManager] Restored PID {self._pid} from file")
            except Exception:
                pass

    def write_pid_file(self, pid: int) -> None:
        try:
            with open(SINGBOX_PID_FILE, "w") as f:
                f.write(str(pid))
        except Exception as e:
            logger.error(f"[SingboxProcessManager] Failed to write PID file: {e}")

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

    # -- teardown ------------------------------------------------------
    def stop(self) -> Optional[int]:
        pid_to_kill = self._pid or (self._process.pid if self._process else None)
        try:
            if self._process is not None:
                self.run_async(self._terminate_process(), timeout=PROCESS_TERMINATE_TIMEOUT + 5)
            elif pid_to_kill:
                self._terminate_pid(pid_to_kill)
        except Exception as e:
            logger.warning(f"[SingboxProcessManager] Async termination failed: {e}")
            if pid_to_kill:
                self._terminate_pid(pid_to_kill)

        self._process = None
        self._pid = None
        if os.path.exists(SINGBOX_PID_FILE):
            try:
                os.remove(SINGBOX_PID_FILE)
            except Exception:
                pass
        self.close_log()
        return pid_to_kill
