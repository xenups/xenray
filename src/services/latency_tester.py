"""Latency testing service for batch server connectivity tests."""
from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional, Tuple

from src.core.logger import logger
from src.services.connection_tester import ConnectionTester


class LatencyTester:
    """Service for batch latency testing of servers."""

    def __init__(
        self,
        on_test_start: Optional[Callable[[dict], None]] = None,
        on_test_complete: Optional[Callable[[dict, bool, str, Optional[dict]], None]] = None,
        on_all_complete: Optional[Callable] = None,
    ):
        """
        Initialize the latency tester.

        Args:
            on_test_start: Called when a test starts, receives profile
            on_test_complete: Called when a test completes, receives (profile, success, result, country_data)
            on_all_complete: Called when all tests are done
        """
        self._on_test_start = on_test_start
        self._on_test_complete = on_test_complete
        self._on_all_complete = on_all_complete
        self._is_testing = False
        self._cancel_flag = False
        self._test_thread: Optional[threading.Thread] = None

        # Cache: {profile_id: (text, color, latency_val)}
        self._results_cache = {}

    @property
    def is_testing(self) -> bool:
        return self._is_testing

    def get_cached_result(self, profile_id: str) -> Optional[Tuple[str, any, int]]:
        """Get cached result for a profile."""
        return self._results_cache.get(profile_id)

    def cancel(self):
        """Cancel ongoing tests."""
        self._cancel_flag = True

    def test_profiles(self, profiles: List[dict], fetch_flags: bool = True):
        """
        Test a list of profiles for latency.

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
            for profile in profiles:
                if self._cancel_flag:
                    break

                # Notify start
                if self._on_test_start:
                    self._on_test_start(profile)

                # Determine if we need to fetch flag
                should_fetch = fetch_flags and not profile.get("country_code")

                # Run test
                success, result, country_data = ConnectionTester.test_connection_sync(
                    profile.get("config", {}),
                    fetch_country=should_fetch,
                )

                # Parse latency value from result (works with any language)
                import re

                latency_val = 999999
                if success:
                    # Extract numeric value from result string
                    match = re.search(r"(\d+)", result)
                    if match:
                        try:
                            latency_val = int(match.group(1))
                        except ValueError:
                            pass

                # Determine color
                import flet as ft

                if not success:
                    color = ft.Colors.RED_400
                elif latency_val < 1000:
                    color = ft.Colors.GREEN_400
                elif latency_val < 2000:
                    color = ft.Colors.ORANGE_400
                else:
                    color = ft.Colors.RED_400

                # Cache result
                pid = profile.get("id")
                if pid:
                    self._results_cache[pid] = (result, color, latency_val)

                # Notify completion
                if self._on_test_complete:
                    self._on_test_complete(profile, success, result, country_data)

                # Small delay to prevent CPU spike
                time.sleep(0.1)

            self._is_testing = False
            if self._on_all_complete:
                self._on_all_complete()

        self._test_thread = threading.Thread(target=_run_tests, daemon=True)
        self._test_thread.start()

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
