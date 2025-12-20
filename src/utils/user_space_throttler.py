"""
User-space bandwidth throttler for TUN interfaces.

Provides fallback rate limiting when OS-level traffic shaping is unavailable.
Uses token bucket algorithm for smooth bandwidth control.
"""

import asyncio
import threading
import time
from typing import Optional

from loguru import logger


class TokenBucketThrottler:
    """
    Token bucket rate limiter for user-space bandwidth control.
    
    This provides a fallback when OS-level traffic shaping (tc, netsh, dnctl) 
    is unavailable or fails. It can be used to throttle any byte stream.
    """
    
    def __init__(self, rate_bytes_per_sec: int = 0, burst_bytes: Optional[int] = None):
        """
        Initialize token bucket throttler.
        
        Args:
            rate_bytes_per_sec: Maximum bytes per second (0 = unlimited)
            burst_bytes: Maximum burst size (defaults to 2x rate)
        """
        self._rate = rate_bytes_per_sec
        self._burst = burst_bytes or (rate_bytes_per_sec * 2 if rate_bytes_per_sec > 0 else 0)
        self._tokens = float(self._burst) if self._burst > 0 else float('inf')
        self._last_update = time.monotonic()
        self._lock = threading.Lock()
        self._enabled = rate_bytes_per_sec > 0
        
        logger.debug(f"[TokenBucket] Initialized: rate={rate_bytes_per_sec/1024:.1f} KB/s, burst={self._burst/1024:.1f} KB")
    
    def set_rate(self, rate_bytes_per_sec: int, burst_bytes: Optional[int] = None):
        """
        Update rate limit.
        
        Args:
            rate_bytes_per_sec: New rate in bytes/sec (0 = unlimited)
            burst_bytes: New burst size (defaults to 2x rate)
        """
        with self._lock:
            self._rate = rate_bytes_per_sec
            self._burst = burst_bytes or (rate_bytes_per_sec * 2 if rate_bytes_per_sec > 0 else 0)
            self._enabled = rate_bytes_per_sec > 0
            
            # Reset tokens to burst size
            self._tokens = float(self._burst) if self._burst > 0 else float('inf')
            self._last_update = time.monotonic()
            
            limit_str = "Unlimited" if rate_bytes_per_sec == 0 else f"{rate_bytes_per_sec/1024:.1f} KB/s"
            logger.debug(f"[TokenBucket] Rate updated: {limit_str}")
    
    def consume(self, num_bytes: int) -> float:
        """
        Consume tokens for the given number of bytes.
        
        Args:
            num_bytes: Number of bytes to consume
            
        Returns:
            Sleep time in seconds (0 if no throttling needed)
        """
        if not self._enabled or num_bytes <= 0:
            return 0.0
        
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            
            # Add tokens based on elapsed time
            if self._rate > 0:
                self._tokens = min(
                    self._burst,
                    self._tokens + (elapsed * self._rate)
                )
            
            self._last_update = now
            
            # Check if we have enough tokens
            if self._tokens >= num_bytes:
                self._tokens -= num_bytes
                return 0.0
            
            # Not enough tokens - calculate sleep time
            tokens_needed = num_bytes - self._tokens
            sleep_time = tokens_needed / self._rate if self._rate > 0 else 0.0
            
            # Consume available tokens
            self._tokens = 0.0
            
            return sleep_time
    
    async def consume_async(self, num_bytes: int):
        """
        Async version of consume - sleeps if throttling needed.
        
        Args:
            num_bytes: Number of bytes to consume
        """
        sleep_time = self.consume(num_bytes)
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
    
    def consume_blocking(self, num_bytes: int):
        """
        Blocking version of consume - sleeps if throttling needed.
        
        Args:
            num_bytes: Number of bytes to consume
        """
        sleep_time = self.consume(num_bytes)
        if sleep_time > 0:
            time.sleep(sleep_time)
    
    def get_stats(self) -> dict:
        """Get current throttler statistics."""
        with self._lock:
            return {
                'rate_bytes_per_sec': self._rate,
                'rate_kb_per_sec': self._rate / 1024,
                'burst_bytes': self._burst,
                'tokens_available': self._tokens,
                'enabled': self._enabled
            }


class UserSpaceThrottler:
    """
    User-space bandwidth throttler for TUN interfaces.
    
    This is a fallback mechanism when OS-level traffic shaping is unavailable.
    It doesn't directly intercept TUN traffic (which would require kernel hooks),
    but provides rate limiting primitives that can be used by the application.
    
    Note: This is a "soft" limit - it relies on the application (Xray/Singbox)
    respecting rate limits. For hard enforcement, OS-level shaping is required.
    """
    
    def __init__(self):
        """Initialize user-space throttler."""
        self._throttler = TokenBucketThrottler(rate_bytes_per_sec=0)
        self._active = False
        logger.info("[UserSpaceThrottler] Initialized (fallback mode)")
    
    def set_limit(self, limit_bytes_per_sec: int) -> bool:
        """
        Set bandwidth limit.
        
        Args:
            limit_bytes_per_sec: Bandwidth limit in bytes/sec (0 = unlimited)
            
        Returns:
            True if limit was set successfully
        """
        try:
            self._throttler.set_rate(limit_bytes_per_sec)
            self._active = limit_bytes_per_sec > 0
            
            limit_str = "Unlimited" if limit_bytes_per_sec == 0 else f"{limit_bytes_per_sec/1024:.1f} KB/s"
            logger.info(f"[UserSpaceThrottler] Limit set: {limit_str} (advisory)")
            return True
            
        except Exception as e:
            logger.error(f"[UserSpaceThrottler] Failed to set limit: {e}")
            return False
    
    def throttle_bytes(self, num_bytes: int):
        """
        Throttle the given number of bytes (blocking).
        
        This can be called by application code to enforce rate limiting.
        
        Args:
            num_bytes: Number of bytes to throttle
        """
        if self._active:
            self._throttler.consume_blocking(num_bytes)
    
    async def throttle_bytes_async(self, num_bytes: int):
        """
        Throttle the given number of bytes (async).
        
        Args:
            num_bytes: Number of bytes to throttle
        """
        if self._active:
            await self._throttler.consume_async(num_bytes)
    
    def get_stats(self) -> dict:
        """Get throttler statistics."""
        stats = self._throttler.get_stats()
        stats['active'] = self._active
        stats['mode'] = 'user-space (advisory)'
        return stats
    
    def is_active(self) -> bool:
        """Check if throttler is actively limiting."""
        return self._active
