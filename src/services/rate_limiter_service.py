"""Rate limiter service for adaptive connection rate control."""

import time
from contextlib import asynccontextmanager
from typing import Optional

from loguru import logger
from throttled.asyncio import RateLimiterType, Throttled, rate_limiter, store

from src.services.network_stability_observer import (NetworkQuality,
                                                     NetworkStabilityObserver)
from src.utils.traffic_shaper import TrafficShaper



class ActiveThroughputController:
    """
    Controls TUN interface throughput based on network quality (Active Rate Control).
    
    Applies logic:
    - EXCELLENT/STABLE: Increase throughput limit (AIMD Additive) or set Unlimited.
    - DEGRADED: Moderate throttling (Start ~10MB/s).
    - UNSTABLE/CRITICAL: Aggressive throttling (Start ~2MB/s) to preserve connectivity.
    """
    def __init__(self):
        self._current_limit_bytes = 0  # 0 = Unlimited
        self._min_limit = 1 * 1024 * 1024    # 1 MB/s minimum (was 50 KB/s)
        self._step_size = 1 * 1024 * 1024    # 1 MB/s additive increase (was 500 KB/s)
        self._last_limit = 0
        self._last_adaptation_time = 0.0
        self._adaptation_cooldown = 5.0  # Minimum 5s between adaptations
        
        # Initialize traffic shaper for actual enforcement
        try:
            self._shaper = TrafficShaper()
            logger.info("[ActiveRateController] Traffic shaper initialized")
        except Exception as e:
            logger.warning(f"[ActiveRateController] Traffic shaper unavailable: {e}")
            self._shaper = None

    def on_quality_change(self, quality: NetworkQuality):
        """Adapt throughput limit based on quality state."""
        import time
        
        # Prevent rapid oscillations with cooldown
        now = time.time()
        if now - self._last_adaptation_time < self._adaptation_cooldown:
            return  # Skip adaptation, too soon since last change
        
        old_limit = self._current_limit_bytes
        
        if quality == NetworkQuality.EXCELLENT:
            # Faster recovery for excellent quality (2x step size)
            if self._current_limit_bytes > 0:
                self._current_limit_bytes += 2 * self._step_size
                # If limit is very high (> 50MB/s), remove it (Unlimited)
                if self._current_limit_bytes > 50 * 1024 * 1024:
                    self._current_limit_bytes = 0
        
        elif quality == NetworkQuality.STABLE:
            # Normal additive increase
            if self._current_limit_bytes > 0:
                self._current_limit_bytes += self._step_size
                # If limit is very high (> 50MB/s), remove it (Unlimited)
                if self._current_limit_bytes > 50 * 1024 * 1024:
                    self._current_limit_bytes = 0 
        
        elif quality == NetworkQuality.DEGRADED:
            # Gentle decrease (75% - was 80%)
            if self._current_limit_bytes == 0:
                self._current_limit_bytes = 5 * 1024 * 1024 # Start throttling at 5MB/s (was 10MB/s)
            self._current_limit_bytes = int(self._current_limit_bytes * 0.75)
            
        elif quality <= NetworkQuality.UNSTABLE:
            # Moderate decrease (75% - was 50%)
            if self._current_limit_bytes == 0:
                 self._current_limit_bytes = 2 * 1024 * 1024 # Start throttling at 2MB/s
            self._current_limit_bytes = max(self._min_limit, int(self._current_limit_bytes * 0.75))
        
        # Smart bypass: Don't throttle healthy networks
        # If quality is STABLE or EXCELLENT and we're using fallback (advisory),
        # set to unlimited to avoid slowing down a good connection
        if quality >= NetworkQuality.STABLE and self._shaper and self._shaper.is_using_fallback():
            if self._current_limit_bytes > 0:
                logger.info(f"[ActiveRateController] Network is {quality.name_str}, bypassing advisory throttling")
                self._current_limit_bytes = 0  # Unlimited for healthy networks
            
        if self._current_limit_bytes != old_limit:
            self._last_adaptation_time = now
            self._apply_limit(self._current_limit_bytes)

    def _apply_limit(self, limit_bytes: int):
        """Apply the calculated limit to the TUN interface."""
        limit_str = "Unlimited" if limit_bytes == 0 else f"{limit_bytes/1024:.1f} KB/s"
        
        # Apply real traffic shaping if available
        if self._shaper:
            success = self._shaper.apply_limit(limit_bytes)
            
            if success:
                # Log which method is being used
                if self._shaper.is_using_fallback():
                    logger.info(f"[ActiveRateController] Applied {limit_str} via user-space fallback (advisory)")
                else:
                    logger.info(f"[ActiveRateController] Applied {limit_str} via platform shaping")
            else:
                logger.warning(f"[ActiveRateController] Failed to apply {limit_str}, limit is advisory only")
        else:
            logger.info(f"[ActiveRateController] Target limit: {limit_str} (shaper unavailable)")
    
    def get_throttler(self):
        """Get the user-space throttler instance (for application use)."""
        if self._shaper:
            return self._shaper.get_throttler()
        return None
    
    def is_using_fallback(self) -> bool:
        """Check if currently using fallback throttler."""
        if self._shaper:
            return self._shaper.is_using_fallback()
        return False


class RateLimiterService:
    """
    Adaptive rate limiter for VPN connection attempts using Token Bucket algorithm.
    
    Implements AIMD-like behavior:
    - Gradually increases rate when connections succeed (Additive Increase)
    - Quickly decreases rate when connections fail (Multiplicative Decrease)
    """

    def __init__(
        self,
        initial_rate: float = 2.0,
        initial_burst: int = 5,
        min_rate: float = 0.5,
        max_rate: float = 5.0,
        adaptation_enabled: bool = True,
        additive_increase: float = 0.5,
        multiplicative_decrease: float = 0.5,
        enable_network_observer: bool = True,
    ):
        """
        Initialize rate limiter service.
        
        Args:
            initial_rate: Initial connection attempts per second
            initial_burst: Maximum burst size (bucket capacity)
            min_rate: Minimum rate during network issues
            max_rate: Maximum rate on stable networks
            adaptation_enabled: Enable dynamic rate adaptation
            additive_increase: Rate increase per adaptation interval (AIMD)
            multiplicative_decrease: Rate multiplier on failure (AIMD)
            enable_network_observer: Enable passive network quality monitoring
        """
        self._current_rate = initial_rate
        self._current_burst = initial_burst
        self._min_rate = min_rate
        self._max_rate = max_rate
        self._adaptation_enabled = adaptation_enabled
        
        # Configurable AIMD parameters
        self._additive_increase = additive_increase
        self._multiplicative_decrease = multiplicative_decrease
        
        # Success/failure tracking for adaptation
        self._consecutive_successes = 0
        self._consecutive_failures = 0
        self._last_adaptation_time = time.time()
        self._adaptation_interval = 5.0  # Adapt every 5 seconds at most
        
        # Track last significant rate change for logging
        self._last_logged_rate = initial_rate
        self._rate_change_threshold = 0.5  # Only log if rate changes by this much
        
        # Create throttled instance
        self._store = store.MemoryStore()
        self._throttle = self._create_throttle()
        
        # Network stability observer (passive monitoring)
        self._observer: Optional[NetworkStabilityObserver] = None
        if enable_network_observer:
            self._observer = NetworkStabilityObserver()
            logger.info("[RateLimiter] Network stability observer enabled")
            
            # Initialize Active Rate Controller and subscribe to events
            self._throughput_controller = ActiveThroughputController()
            self._observer.add_callback(self._throughput_controller.on_quality_change)
        
        logger.info(
            f"[RateLimiter] Initialized: rate={self._current_rate} conn/sec, "
            f"burst={self._current_burst}, AIMD=(+{additive_increase}, ×{multiplicative_decrease})"
        )

    def _create_throttle(self) -> Throttled:
        """Create a new Throttled instance with current parameters."""
        return Throttled(
            using=RateLimiterType.TOKEN_BUCKET.value,
            quota=rate_limiter.per_sec(
                limit=int(self._current_rate),
                burst=self._current_burst
            ),
            store=self._store,
        )

    @asynccontextmanager
    async def acquire(self, key: str = "vpn_connection"):
        """
        Context manager to rate-limit connection attempts.
        
        Args:
            key: Unique key for this rate limit (e.g., "vpn_connection", "server_123")
            
        Yields:
            None
        """
        # Check rate limit
        result = await self._throttle.limit(key, cost=1)
        
        if result.limited:
            retry_after = result.retry_after or 1.0
            logger.warning(
                f"[RateLimiter] Rate limited (key={key}). "
                f"Retry after {retry_after:.2f}s (rate: {self._current_rate} conn/sec)"
            )
            # Wait before retrying to prevent bursts
            import asyncio
            await asyncio.sleep(retry_after)
            
            # Re-check after waiting to ensure smooth pacing
            result = await self._throttle.limit(key, cost=1)
            if result.limited:
                # Still limited, wait a bit more
                await asyncio.sleep(0.5)
        
        try:
            yield
            # Connection attempt succeeded
            if self._adaptation_enabled:
                self._on_success()
        except Exception as e:
            # Connection attempt failed
            if self._adaptation_enabled:
                self._on_failure()
            raise

    def check_limit_sync(self, key: str = "vpn_connection") -> tuple[bool, float]:
        """
        Lightweight synchronous rate limit check (non-blocking).
        
        Args:
            key: Unique key for this rate limit
            
        Returns:
            Tuple of (should_proceed, wait_time_seconds)
        """
        # Simple token bucket check without async overhead
        # This is a lightweight check that doesn't block
        # For simplicity, we allow the connection and let the async handler
        # do the actual rate limiting. This avoids sync/async mixing.
        return (True, 0.0)

    def report_success(self, key: str = "vpn_connection"):
        """
        Report successful connection for adaptive rate adjustment.
        
        Args:
            key: Connection key (for logging purposes)
        """
        if self._adaptation_enabled:
            self._on_success()
        
        # Check network quality and adapt if observer is enabled
        if self._observer:
            quality = self._observer.get_quality()
            self._adapt_to_quality(quality)

    def report_failure(self, key: str = "vpn_connection"):
        """
        Report failed connection for adaptive rate adjustment.
        
        Args:
            key: Connection key (for logging purposes)
        """
        if self._adaptation_enabled:
            self._on_failure()
        
        # Notify observer of failure (passive signal)
        if self._observer:
            self._observer.on_timeout()  # Treat connection failure as timeout
            quality = self._observer.get_quality()
            self._adapt_to_quality(quality)

    def _on_success(self):
        """Handle successful connection attempt for adaptive rate adjustment."""
        self._consecutive_successes += 1
        self._consecutive_failures = 0
        
        # Gradually increase rate (Additive Increase)
        if self._should_adapt():
            old_rate = self._current_rate
            self._current_rate = min(
                self._max_rate,
                self._current_rate + self._additive_increase
            )
            
            # Only recreate throttle if rate changed significantly
            if abs(self._current_rate - old_rate) >= 0.1:
                self._throttle = self._create_throttle()
                self._last_adaptation_time = time.time()
                
                # Only log significant changes
                if abs(self._current_rate - self._last_logged_rate) >= self._rate_change_threshold:
                    logger.info(
                        f"[RateLimiter] Rate increased: {old_rate:.1f} → {self._current_rate:.1f} conn/sec "
                        f"(successes: {self._consecutive_successes})"
                    )
                    self._last_logged_rate = self._current_rate

    def _on_failure(self):
        """Handle failed connection attempt for adaptive rate adjustment."""
        self._consecutive_failures += 1
        self._consecutive_successes = 0
        
        # Quickly decrease rate (Multiplicative Decrease)
        if self._should_adapt():
            old_rate = self._current_rate
            self._current_rate = max(
                self._min_rate,
                self._current_rate * self._multiplicative_decrease
            )
            
            # Only recreate throttle if rate changed significantly
            if abs(self._current_rate - old_rate) >= 0.1:
                self._throttle = self._create_throttle()
                self._last_adaptation_time = time.time()
                
                # Always log failures (important for debugging)
                logger.warning(
                    f"[RateLimiter] Rate decreased: {old_rate:.1f} → {self._current_rate:.1f} conn/sec "
                    f"(failures: {self._consecutive_failures})"
                )
                self._last_logged_rate = self._current_rate

    def _should_adapt(self) -> bool:
        """Check if enough time has passed since last adaptation."""
        return (time.time() - self._last_adaptation_time) >= self._adaptation_interval
    
    def _adapt_to_quality(self, quality: NetworkQuality):
        """
        Adapt rate based on network quality (smoothed transitions).
        
        Args:
            quality: Current network quality state
        """
        old_rate = self._current_rate
        
        if quality == NetworkQuality.EXCELLENT:
            # Gradual increase
            self._current_rate = min(self._max_rate, self._current_rate + 0.5)
        elif quality == NetworkQuality.STABLE:
            # Slight increase if stable for a while (handled by observer)
            # No immediate change
            pass
        elif quality == NetworkQuality.DEGRADED:
            # Gentle decrease (10%)
            self._current_rate = max(self._min_rate, self._current_rate * 0.9)
        elif quality == NetworkQuality.UNSTABLE:
            # Moderate decrease (30%) - less aggressive
            self._current_rate = max(self._min_rate, self._current_rate * 0.7)
        elif quality == NetworkQuality.CRITICAL:
            # Aggressive but gradual approach to minimum
            target = max(self._min_rate, self._current_rate * 0.5)
            self._current_rate = max(self._min_rate, target)
        
        # Only recreate throttle if rate changed significantly
        if abs(self._current_rate - old_rate) >= 0.1:
            self._throttle = self._create_throttle()
            
            # Log quality-based adaptation
            if abs(self._current_rate - self._last_logged_rate) >= self._rate_change_threshold:
                logger.info(
                    f"[RateLimiter] Quality-based adaptation: {old_rate:.1f} → {self._current_rate:.1f} conn/sec "
                    f"(quality: {quality.name_str})"
                )
                self._last_logged_rate = self._current_rate

    async def get_current_state(self, key: str = "vpn_connection") -> dict:
        """
        Get current rate limiter state.
        
        Args:
            key: Key to check state for
            
        Returns:
            Dictionary with current rate, burst, and statistics
        """
        state = await self._throttle.peek(key)
        
        return {
            "current_rate": self._current_rate,
            "current_burst": self._current_burst,
            "min_rate": self._min_rate,
            "max_rate": self._max_rate,
            "consecutive_successes": self._consecutive_successes,
            "consecutive_failures": self._consecutive_failures,
            "adaptation_enabled": self._adaptation_enabled,
            "aimd_params": {
                "additive_increase": self._additive_increase,
                "multiplicative_decrease": self._multiplicative_decrease,
            },
            "remaining_tokens": state.remaining if state else None,
            "retry_after": state.retry_after if state else None,
        }

    def reset_statistics(self):
        """Reset success/failure counters."""
        self._consecutive_successes = 0
        self._consecutive_failures = 0
        logger.info("[RateLimiter] Statistics reset")
    
    @property
    def observer(self) -> Optional[NetworkStabilityObserver]:
        """Get the network stability observer instance."""
        return self._observer

    def update_parameters(
        self,
        rate: Optional[float] = None,
        burst: Optional[int] = None,
        min_rate: Optional[float] = None,
        max_rate: Optional[float] = None,
        additive_increase: Optional[float] = None,
        multiplicative_decrease: Optional[float] = None,
    ):
        """
        Manually update rate limiter parameters.
        
        Args:
            rate: New rate (conn/sec)
            burst: New burst size
            min_rate: New minimum rate
            max_rate: New maximum rate
            additive_increase: New AIMD additive increase value
            multiplicative_decrease: New AIMD multiplicative decrease value
        """
        needs_recreation = False
        
        if rate is not None and abs(rate - self._current_rate) >= 0.1:
            self._current_rate = max(self._min_rate, min(self._max_rate, rate))
            needs_recreation = True
            
        if burst is not None and burst != self._current_burst:
            self._current_burst = burst
            needs_recreation = True
            
        if min_rate is not None:
            self._min_rate = min_rate
            
        if max_rate is not None:
            self._max_rate = max_rate
            
        if additive_increase is not None:
            self._additive_increase = additive_increase
            
        if multiplicative_decrease is not None:
            self._multiplicative_decrease = multiplicative_decrease
        
        # Only recreate if rate or burst changed significantly
        if needs_recreation:
            self._throttle = self._create_throttle()
            logger.info(
                f"[RateLimiter] Parameters updated: rate={self._current_rate:.1f}, "
                f"burst={self._current_burst}"
            )
