"""Latency testing service for batch server connectivity tests."""

from __future__ import annotations

import asyncio
import re
import threading
import time
from typing import Any, Callable, List, Optional, Tuple

import flet as ft

from src.core.logger import logger
from src.services.connection_tester import ConnectionTester

# Upper bound on concurrently running per-node tests. Keeps Xray instance
# spawns reasonable while still testing all nodes in parallel (asyncio.gather).
MAX_CONCURRENT_TESTS = 10


class LatencyTester:
    """Service for batch latency testing of servers."""

    def __init__(
        self,
        on_test_start: Optional[Callable[[dict], None]] = None,
        on_test_complete: Optional[Callable[[dict, bool, str, Optional[dict]], None]] = None,
        on_all_complete: Optional[Callable] = None,
        app_context=None,
    ):
        """
        Initialize the latency tester.

        Args:
            on_test_start: Called when a test starts, receives profile
            on_test_complete: Called when a test completes, receives (profile, success, result, country_data)
            on_all_complete: Called when all tests are done
            app_context: AppContext instance for resolving chains
        """
        self._on_test_start = on_test_start
        self._on_test_complete = on_test_complete
        self._on_all_complete = on_all_complete
        self._app_context = app_context
        self._is_testing = False
        self._cancel_flag = False
        self._test_thread: Optional[threading.Thread] = None

        # Cache: {profile_id: (text, color, latency_val)}
        self._results_cache: dict = {}

    @property
    def is_testing(self) -> bool:
        return self._is_testing

    def get_cached_result(self, profile_id: str) -> Optional[Tuple[str, Any, int]]:
        """Get cached result for a profile."""
        return self._results_cache.get(profile_id)

    def cancel(self):
        """Cancel ongoing tests."""
        self._cancel_flag = True

    def test_profiles(self, profiles: List[dict], fetch_flags: bool = True):
        """
        Test a list of profiles for latency, concurrently via ``asyncio.gather``.

        Args:
            profiles: List of profile dicts with 'id' and 'config'
            fetch_flags: Whether to fetch country data for profiles without it
        """
        if self._is_testing:
            logger.debug("Latency test already in progress")
            return

        self._is_testing = True
        self._cancel_flag = False

        def _run_tests():
            try:
                asyncio.run(self._run_tests_async(profiles, fetch_flags))
            except Exception as e:
                logger.error(f"[LatencyTester] Batch latency test error: {e}")
            finally:
                self._is_testing = False
                if self._on_all_complete:
                    try:
                        self._on_all_complete()
                    except Exception:
                        pass

        self._test_thread = threading.Thread(target=_run_tests, daemon=True)
        self._test_thread.start()

    async def _run_tests_async(self, profiles: List[dict], fetch_flags: bool) -> None:
        """Run per-profile tests concurrently with a bounded semaphore."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TESTS)

        async def _test_one(profile: dict) -> None:
            if self._cancel_flag:
                return

            if self._on_test_start:
                try:
                    self._on_test_start(profile)
                except Exception:
                    pass

            # Chains don't have pre-built config - need to build it (blocking).
            config = profile.get("config")
            is_chain = profile.get("_is_chain") or profile.get("items") is not None
            if is_chain and (not config or not config.get("outbounds")) and self._app_context:
                config = await asyncio.to_thread(self._build_chain_config, profile)
                if config is None:
                    return  # error already reported via on_test_complete

            should_fetch = fetch_flags and not profile.get("country_code")

            async with semaphore:
                success, result, country_data = await asyncio.to_thread(
                    ConnectionTester.test_connection_sync,
                    config if config else {},
                    should_fetch,
                )

            latency_val = self._parse_latency(success, result)
            color = self._latency_color(success, latency_val)

            pid = profile.get("id")
            if pid:
                self._results_cache[pid] = (result, color, latency_val)

            if self._on_test_complete:
                try:
                    self._on_test_complete(profile, success, result, country_data)
                except Exception:
                    pass

        await asyncio.gather(*(_test_one(p) for p in profiles))

    def _build_chain_config(self, profile: dict) -> Optional[dict]:
        """Build a chain config (blocking) or report failure."""
        try:
            from src.services.xray_config_processor import XrayConfigProcessor

            processor = XrayConfigProcessor(self._app_context)
            success, chain_config, error_msg = processor.build_chain_config(profile)
            if not success:
                logger.warning(f"Chain config build failed: {error_msg}")
                if self._on_test_complete:
                    self._on_test_complete(profile, False, error_msg, None)
                return None
            return chain_config
        except Exception as e:
            logger.error(f"Failed to build chain config: {e}")
            if self._on_test_complete:
                self._on_test_complete(profile, False, str(e), None)
            return None

    @staticmethod
    def _parse_latency(success: bool, result: str) -> int:
        """Extract the numeric latency value from the localized result string."""
        latency_val = 999999
        if success:
            match = re.search(r"(\d+)", result)
            if match:
                try:
                    latency_val = int(match.group(1))
                except ValueError:
                    pass
        return latency_val

    @staticmethod
    def _latency_color(success: bool, latency_val: int) -> str:
        """Map a latency result to the UI color."""
        if not success:
            return ft.Colors.RED_400
        if latency_val < 1000:
            return ft.Colors.GREEN_400
        if latency_val < 2000:
            return ft.Colors.ORANGE_400
        return ft.Colors.RED_400

    def clear_cache(self):
        """Clear the results cache."""
        self._results_cache.clear()

    def restart_testing(self, profiles: List[dict]):
        """
        Restart testing with a new list of profiles.
        Cancels current test and queues the new list.
        """
        self.cancel()

        def _restart_task():
            # Wait for current test to stop
            start_wait = time.time()
            while self._is_testing:
                if time.time() - start_wait > 2.0:
                    # Force break if stuck
                    break
                time.sleep(0.05)

            # Start new test
            self.test_profiles(profiles)

        # Run restart logic in a separate thread to avoid blocking
        threading.Thread(target=_restart_task, daemon=True).start()
