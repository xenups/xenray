"""SNI-spoof service lifecycle — in-process asyncio listener task + fail-soft.

start():
  1. Reads the persisted config (SettingsRepository).
  2. Checks prerequisites — pydivert importable AND process elevated
     (WinDivert opens a kernel driver; without admin the injector thread dies
     and we would otherwise relay without spoofing).
     When prerequisites are missing: log warning, publish stopped status,
     return False (fail-soft). Nothing is spawned.
  3. Spawns the listener as an in-process asyncio task and publishes status.
stop():  cancels the task, publishes stopped status.

Parent-PID watch: a short background thread polls the Xray PID file
(``XRAY_PID_FILE``); when Xray dies while we are running, the listener task is
cancelled (self-healing cascade — the core-health monitor owns the Xray side).
"""

import asyncio
import os
import threading

import loguru

from src.core.constants import XRAY_PID_FILE
from src.core.event_bus import TOPIC_SNI_SPOOF_CHANGED, EventBus
from src.services.sni_spoof.config import build_config
from src.services.sni_spoof.factory import SpoofEngineFactory
from src.services.sni_spoof.listener import configure, run_listener
from src.services.sni_spoof.models import SpoofEngineConfig, SpoofMethod
from src.utils.process_utils import ProcessUtils

logger = loguru.logger

STATUS_STOPPED = "stopped"
STATUS_RUNNING = "running"
STATUS_FAILED = "failed"


def _prerequisites_ok() -> tuple:
    """(ok, reason). Requires pydivert importable + admin rights.

    WinDivert.dll ships with pip's ``pydivert`` wheel; the kernel driver needs
    an elevated shell. Non-Windows always fails here.
    """
    try:
        import pydivert

        if pydivert is None:
            return False, "pydivert not installed"
    except Exception:
        return False, "pydivert not installed"
    if not ProcessUtils.is_admin():
        return False, "administrator privileges required (WinDivert kernel driver)"
    return True, ""


class SniSpoofService:
    """Lifecycle facade for the SNI-spoof listener task."""

    def __init__(self, settings_repo=None, event_bus: EventBus = None):
        self._settings_repo = settings_repo
        self._event_bus = event_bus or EventBus.get_instance()
        self._task = None
        self.status = STATUS_STOPPED
        self._watcher_stop = threading.Event()
        self._watcher = None
        self._loop = None
        self._loop_thread = None
        self._loop_ready = threading.Event()
        self._engine = None  # BaseSpoofEngine built from typed config

    def _build_engine_from_config(self, config: dict):
        """Build a typed SpoofEngineConfig + engine via the factory.

        Pure data mapping — no behaviour change; the listener still receives the
        same raw config via ``configure()``.
        """
        method = SpoofMethod(config.get("BYPASS_METHOD", "wrong_seq"))
        engine_config = SpoofEngineConfig(
            fake_sni=config.get("FAKE_SNI", "chatgpt.com"),
            connect_ip=config.get("CONNECT_IP", "185.193.30.94"),
            connect_port=config.get("CONNECT_PORT", 443),
            listen_host=config.get("LISTEN_HOST", "127.0.0.1"),
            listen_port=config.get("LISTEN_PORT", 40443),
            method=method,
            data_mode=config.get("DATA_MODE", "tls"),
        )
        self._engine = SpoofEngineFactory.create(engine_config)
        return self._engine

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> bool:
        """Start the listener. Returns False (fail-soft) when prerequisites
        are missing — never raises."""
        if self.running:
            return True
        ok, reason = _prerequisites_ok()
        if not ok:
            logger.warning(f"[SniSpoof] start refused: {reason}")
            self.status = STATUS_FAILED
            self._publish(self.status)
            return False

        config = build_config(self._settings_repo)
        logger.info(f"[SniSpoof] starting listener with {config}")
        # Build the typed engine (factory) — pure mapping, no behaviour change.
        try:
            self._build_engine_from_config(config)
        except Exception as e:
            logger.warning(f"[SniSpoof] engine build failed (non-fatal): {e}")
        # Persisted config must reach the actual listener before the task runs.
        configure(config)

        self._start_listener_loop()

        self._watcher_stop.clear()
        self._watcher = threading.Thread(target=self._watch_parent, daemon=True, name="sni-spoof-parent-watch")
        self._watcher.start()
        self.status = STATUS_RUNNING
        self._publish(self.status)
        return True

    def _listener_coro(self):
        """Wrap the blocking listener so a crash is logged, never a raise."""

        async def _run():
            try:
                await run_listener()
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("[SniSpoof] listener task crashed")

        return _run()

    def _start_listener_loop(self) -> None:
        """Run the listener on a dedicated asyncio loop in its own daemon thread.

        Fixes the fragile "create_task on a maybe-never-run loop" path: the
        service always owns a loop, so scheduling never depends on whether the
        caller thread has (or runs) a loop. Bounded wait until the task exists.
        """
        self._loop_ready.clear()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True, name="sni-spoof-listener-loop")
        self._loop_thread.start()
        self._loop_ready.wait(5.0)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            self._task = loop.create_task(self._listener_coro())
        except Exception:
            logger.exception("[SniSpoof] failed to create listener task")
        finally:
            self._loop_ready.set()
        try:
            loop.run_forever()
        finally:
            # Drain any remaining tasks (the cancelled listener, spawned relay/
            # handler tasks) so we never emit "Task was destroyed but it is pending!"
            try:
                pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for t in pending:
                    t.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                logger.debug("[SniSpoof] loop drain finished with exception")
            loop.close()
            self._task = None
            self._loop = None
            self._loop_thread = None
            if self.status == STATUS_RUNNING:
                self.status = STATUS_FAILED
                self._publish(self.status)

    def stop(self) -> bool:
        """Cancel the listener task, stop the loop, and stop the watcher thread."""
        self._watcher_stop.set()
        # Publish stopped state before draining the loop so the loop thread's
        # cleanup finally-block can never overwrite it back to FAILED.
        self.status = STATUS_STOPPED
        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception:
            pass
        self._shutdown_listener_loop()
        # Give the loop thread a moment to run its finally (closes the listen
        # socket + clears _task/_loop), so a reconnect right after this stop can
        # re-bind 127.0.0.1:LISTEN_PORT instead of hitting "address in use".
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=2.0)
        self._publish(self.status)
        return True

    def _shutdown_listener_loop(self) -> None:
        """Thread-safe shutdown: schedule cancel + loop stop on the listener loop."""
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._cancel_and_stop)
        self._task = None

    def _cancel_and_stop(self) -> None:
        """Run on the listener loop: cancel the task, stop the loop when done."""
        loop = self._loop
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            task.add_done_callback(lambda _t: loop.stop() if loop is not None else None)
        elif loop is not None and loop.is_running():
            loop.stop()

    def _watch_parent(self) -> None:
        """Exit the listener when the Xray PID file disappears (Xray died)."""
        while not self._watcher_stop.wait(2.0):
            if not os.path.exists(XRAY_PID_FILE):
                if self.running:
                    logger.warning("[SniSpoof] Xray PID file gone — stopping listener")
                    self.stop()
                return

    def _publish(self, status: str) -> None:
        try:
            self._event_bus.publish(TOPIC_SNI_SPOOF_CHANGED, {"status": status})
        except Exception:
            logger.debug("[SniSpoof] status publish failed (no listeners)")

    def dispose(self) -> None:
        self.stop()


# --------------------------------------------------------------------------- #
# Shared instance (the lifecycle bridge lives in bridge.py)
# --------------------------------------------------------------------------- #

_SHARED_LOCK = threading.Lock()
_SHARED_SERVICE = None


def get_sni_spoof_service(settings_repo=None) -> SniSpoofService:
    """Return the process-shared SniSpoofService, creating it once.

    XrayService and the UI lifecycle bridge (bridge.py) must drive the SAME
    instance so a toggle lands on the listener a connection actually started.
    """
    global _SHARED_SERVICE
    with _SHARED_LOCK:
        if _SHARED_SERVICE is None:
            _SHARED_SERVICE = SniSpoofService(settings_repo=settings_repo)
        return _SHARED_SERVICE


def reset_shared_service_for_tests() -> None:
    """Test hook: drop and stop the shared service (bridge.py owns its own reset)."""
    global _SHARED_SERVICE
    with _SHARED_LOCK:
        svc = _SHARED_SERVICE
        _SHARED_SERVICE = None
    if svc is not None:
        try:
            svc.stop()
        except Exception:
            pass
