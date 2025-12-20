"""Unit tests for RateLimiterService."""

import asyncio
import time

import pytest

from src.services.rate_limiter_service import RateLimiterService


class TestRateLimiterService:
    """Test suite for RateLimiterService."""

    def test_initialization(self):
        """Test rate limiter initializes with correct parameters."""
        limiter = RateLimiterService(
            initial_rate=2.0,
            initial_burst=5,
            min_rate=0.5,
            max_rate=5.0,
            adaptation_enabled=True,
        )
        
        assert limiter._current_rate == 2.0
        assert limiter._current_burst == 5
        assert limiter._min_rate == 0.5
        assert limiter._max_rate == 5.0
        assert limiter._adaptation_enabled is True

    def test_check_limit_sync_always_allows(self):
        """Test that check_limit_sync is non-blocking and always allows."""
        limiter = RateLimiterService(
            initial_rate=10.0,  # High rate for testing
            initial_burst=10,
            adaptation_enabled=False,
        )
        
        # Should always allow (non-blocking check)
        should_proceed, wait_time = limiter.check_limit_sync("test_key")
        assert should_proceed is True
        assert wait_time == 0.0

    @pytest.mark.asyncio
    async def test_async_acquire_rate_limiting(self):
        """Test that async acquire enforces rate limits."""
        limiter = RateLimiterService(
            initial_rate=1.0,  # 1 connection per second
            initial_burst=2,   # Allow 2 rapid connections
            adaptation_enabled=False,
        )
        
        # First two should succeed quickly (burst)
        start = time.time()
        async with limiter.acquire("test_key"):
            pass
        async with limiter.acquire("test_key"):
            pass
        burst_time = time.time() - start
        
        # Should be fast (no waiting)
        assert burst_time < 0.5
        
        # Third should be rate limited (will wait)
        start = time.time()
        async with limiter.acquire("test_key"):
            pass
        elapsed = time.time() - start
        
        # Should have waited
        assert elapsed >= 0.5

    def test_report_success_increases_rate(self):
        """Test that reporting success gradually increases rate."""
        limiter = RateLimiterService(
            initial_rate=2.0,
            initial_burst=5,
            min_rate=0.5,
            max_rate=5.0,
            adaptation_enabled=True,
        )
        
        initial_rate = limiter._current_rate
        
        # Simulate successful connections
        for _ in range(3):
            limiter.report_success()
            time.sleep(0.1)
        
        # Wait for adaptation interval
        time.sleep(6)
        limiter.report_success()
        
        # Rate should have increased
        assert limiter._current_rate > initial_rate
        assert limiter._current_rate <= limiter._max_rate

    def test_report_failure_decreases_rate(self):
        """Test that reporting failure quickly decreases rate."""
        limiter = RateLimiterService(
            initial_rate=4.0,
            initial_burst=5,
            min_rate=0.5,
            max_rate=5.0,
            adaptation_enabled=True,
        )
        
        initial_rate = limiter._current_rate
        
        # Wait for adaptation interval
        time.sleep(6)
        
        # Simulate failed connection
        limiter.report_failure()
        
        # Rate should have decreased (multiplicative decrease)
        assert limiter._current_rate < initial_rate
        assert limiter._current_rate >= limiter._min_rate

    def test_rate_bounds(self):
        """Test that rate stays within min/max bounds."""
        limiter = RateLimiterService(
            initial_rate=3.0,
            initial_burst=5,
            min_rate=1.0,
            max_rate=5.0,
            adaptation_enabled=True,
        )
        
        # Try to increase beyond max
        time.sleep(6)
        for _ in range(10):
            limiter.report_success()
            time.sleep(6)
        
        assert limiter._current_rate <= limiter._max_rate
        
        # Try to decrease below min
        for _ in range(10):
            time.sleep(6)
            limiter.report_failure()
        
        assert limiter._current_rate >= limiter._min_rate

    @pytest.mark.asyncio
    async def test_async_acquire(self):
        """Test async acquire context manager."""
        limiter = RateLimiterService(
            initial_rate=10.0,
            initial_burst=10,
            adaptation_enabled=False,
        )
        
        # Should allow connection
        async with limiter.acquire("test_key"):
            pass  # Connection logic would go here

    @pytest.mark.asyncio
    async def test_async_acquire_with_success(self):
        """Test async acquire reports success correctly."""
        limiter = RateLimiterService(
            initial_rate=2.0,
            initial_burst=5,
            min_rate=0.5,
            max_rate=5.0,
            adaptation_enabled=True,
        )
        
        initial_successes = limiter._consecutive_successes
        
        async with limiter.acquire("test_key"):
            pass  # Successful connection
        
        assert limiter._consecutive_successes == initial_successes + 1
        assert limiter._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_async_acquire_with_failure(self):
        """Test async acquire reports failure correctly."""
        limiter = RateLimiterService(
            initial_rate=2.0,
            initial_burst=5,
            min_rate=0.5,
            max_rate=5.0,
            adaptation_enabled=True,
        )
        
        initial_failures = limiter._consecutive_failures
        
        try:
            async with limiter.acquire("test_key"):
                raise Exception("Simulated connection failure")
        except Exception:
            pass
        
        assert limiter._consecutive_failures == initial_failures + 1
        assert limiter._consecutive_successes == 0

    @pytest.mark.asyncio
    async def test_get_current_state(self):
        """Test getting current rate limiter state."""
        limiter = RateLimiterService(
            initial_rate=2.0,
            initial_burst=5,
            min_rate=0.5,
            max_rate=5.0,
            adaptation_enabled=True,
        )
        
        state = await limiter.get_current_state()
        
        assert state["current_rate"] == 2.0
        assert state["current_burst"] == 5
        assert state["min_rate"] == 0.5
        assert state["max_rate"] == 5.0
        assert state["adaptation_enabled"] is True
        assert "consecutive_successes" in state
        assert "consecutive_failures" in state

    def test_reset_statistics(self):
        """Test resetting success/failure counters."""
        limiter = RateLimiterService(
            initial_rate=2.0,
            adaptation_enabled=True,
        )
        
        # Simulate some activity
        limiter.report_success()
        limiter.report_success()
        limiter.report_failure()
        
        assert limiter._consecutive_failures > 0
        
        # Reset
        limiter.reset_statistics()
        
        assert limiter._consecutive_successes == 0
        assert limiter._consecutive_failures == 0

    def test_update_parameters(self):
        """Test manually updating rate limiter parameters."""
        limiter = RateLimiterService(
            initial_rate=2.0,
            initial_burst=5,
            min_rate=0.5,
            max_rate=5.0,
        )
        
        # Update parameters
        limiter.update_parameters(
            rate=3.0,
            burst=10,
            min_rate=1.0,
            max_rate=6.0,
        )
        
        assert limiter._current_rate == 3.0
        assert limiter._current_burst == 10
        assert limiter._min_rate == 1.0
        assert limiter._max_rate == 6.0

    def test_adaptation_disabled(self):
        """Test that adaptation can be disabled."""
        limiter = RateLimiterService(
            initial_rate=2.0,
            adaptation_enabled=False,
        )
        
        initial_rate = limiter._current_rate
        
        # Report success/failure
        time.sleep(6)
        limiter.report_success()
        limiter.report_failure()
        
        # Rate should not change
        assert limiter._current_rate == initial_rate
