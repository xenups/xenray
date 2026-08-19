"""StartupWarmupManager - background initialization orchestrator executing concurrent startup tasks."""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Callable, Optional

from src.core.logger import logger
from src.core.system_info_cache import system_info_cache
from src.services.connection.ping_service import PRIORITY_MANUAL, ping_manager

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class StartupWarmupManager:
    """Central startup orchestrator executing pre-warming tasks concurrently before rendering the main shell."""

    # Tight budget the splash waits for the active-server ping before dismissing.
    ACTIVE_PING_TIMEOUT_SECONDS = 1.5

    def __init__(self, main_window: Optional[MainWindow] = None) -> None:
        self._mw = main_window
        self._warmed_up: bool = False
        self._warmup_lock = threading.Lock()

    def set_main_window(self, main_window: MainWindow) -> None:
        """Bind main window coordinator."""
        self._mw = main_window

    async def execute_startup_pipeline(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Execute all startup tasks, holding the splash until the active ping lands."""
        try:
            logger.info("[StartupWarmupManager] Beginning startup pre-warming pipeline...")

            if progress_callback:
                progress_callback("Warming System Info & Diagnostics...")

            loop = asyncio.get_running_loop()

            # Phase 1 — concurrent warmup that must complete before the active ping:
            # views MUST be mounted (DashboardPage subscribes to the ping EventBus
            # topic in __init__) so the pre-fetched ping is rendered instantly.
            task_system_info = loop.run_in_executor(None, system_info_cache.warmup_system_info)
            task_logs = self._warmup_logs_engine()
            task_views = self._warmup_views_and_navigation()
            task_i18n = self._warmup_i18n()

            await asyncio.gather(
                task_system_info,
                task_logs,
                task_views,
                task_i18n,
                return_exceptions=True,
            )

            # Phase 2 — measure the active server ping (awaited up to the tight
            # timeout) so the splash stays up and the dashboard is pre-populated.
            await self._warmup_active_server_ping()

            with self._warmup_lock:
                self._warmed_up = True

            logger.info("[StartupWarmupManager] Pipeline complete — zero-latency startup ready.")
            return True
        except Exception as e:
            logger.error(f"[StartupWarmupManager] Error during startup pre-warming: {e}")
            return False

    async def _warmup_i18n(self) -> None:
        """Load the remaining translation files in the background during the splash.

        Only the active language is loaded eagerly for a fast splash; the other
        locale JSONs are prefetched here (off the event loop) so a later language
        switch is instant.
        """
        try:
            from src.core.i18n import load_all_languages

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, load_all_languages)
        except Exception as e:
            logger.debug(f"[StartupWarmupManager] i18n pre-fill non-critical error: {e}")

    async def _warmup_logs_engine(self) -> None:
        """Pre-read and parse initial log streams into memory for instant LogsPage loading."""
        try:
            if self._mw and hasattr(self._mw, "_log_viewer") and self._mw._log_viewer:
                if hasattr(self._mw._log_viewer, "load_history"):
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, self._mw._log_viewer.load_history)
        except Exception as e:
            logger.debug(f"[StartupWarmupManager] Log engine pre-fill non-critical error: {e}")

    async def _warmup_active_server_ping(self) -> None:
        """Run the active server ping at PRIORITY_MANUAL and pre-populate the dashboard.

        Dispatched through :class:`PingManager` and awaited with a tight timeout so
        the splash holds until the measured ping is published (or the budget
        expires) — the DashboardPage then renders the exact value with zero delay.
        """
        try:
            if not (self._mw and hasattr(self._mw, "_latency_monitor_handler") and self._mw._latency_monitor_handler):
                return
            profile = getattr(self._mw, "_selected_profile", None)
            if not profile:
                return

            handler = self._mw._latency_monitor_handler
            pid = str(profile.get("id"))

            def _run():
                result = handler.run_active_ping_sync(profile)
                if result:
                    # Publish (marshaled to the UI thread) so DashboardPage /
                    # ServerCard show the ping immediately behind the splash.
                    handler._on_ping_result(profile, *result)
                return result

            future = ping_manager.submit_and_get_future(
                PRIORITY_MANUAL,
                f"startup_ping_{pid}",
                _run,
            )
            if future is not None:
                try:
                    await asyncio.wait_for(
                        asyncio.wrap_future(future),
                        timeout=self.ACTIVE_PING_TIMEOUT_SECONDS,
                    )
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass  # budget exceeded — dismiss the splash; ping lands when ready
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[StartupWarmupManager] Active server ping warmup error: {e}")

    async def _warmup_views_and_navigation(self) -> None:
        """Pre-instantiate and warm up view controllers into memory for instant tab switching."""
        try:
            if self._mw and hasattr(self._mw, "_ui_builder") and self._mw._ui_builder:
                self._mw._ui_builder.build_stitch_views()
        except Exception as e:
            logger.debug(f"[StartupWarmupManager] View navigation pre-render non-critical error: {e}")

    @property
    def is_warmed_up(self) -> bool:
        """Check if warmup pipeline has finished."""
        with self._warmup_lock:
            return self._warmed_up
