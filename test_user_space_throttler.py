"""
Test user-space throttler fallback mechanism.
"""

import time
from src.utils.user_space_throttler import TokenBucketThrottler, UserSpaceThrottler


def test_token_bucket_basic():
    """Test basic token bucket functionality."""
    # 1 KB/s rate
    throttler = TokenBucketThrottler(rate_bytes_per_sec=1024, burst_bytes=2048)
    
    # Should not throttle small amount
    sleep_time = throttler.consume(512)
    assert sleep_time == 0.0, "Small consume should not require sleep"
    
    # Should throttle large amount
    sleep_time = throttler.consume(3000)
    assert sleep_time > 0, "Large consume should require sleep"
    print(f"✓ Token bucket throttles correctly (sleep: {sleep_time:.3f}s)")


def test_token_bucket_unlimited():
    """Test unlimited mode."""
    throttler = TokenBucketThrottler(rate_bytes_per_sec=0)
    
    # Should never throttle
    sleep_time = throttler.consume(1000000)
    assert sleep_time == 0.0, "Unlimited should never throttle"
    print("✓ Unlimited mode works")


def test_user_space_throttler():
    """Test user-space throttler."""
    throttler = UserSpaceThrottler()
    
    # Set limit
    success = throttler.set_limit(1024 * 100)  # 100 KB/s
    assert success, "Should set limit successfully"
    
    # Check stats
    stats = throttler.get_stats()
    assert stats['active'] == True, "Should be active"
    assert stats['rate_kb_per_sec'] == 100, "Rate should be 100 KB/s"
    print(f"✓ User-space throttler configured: {stats}")
    
    # Test unlimited
    throttler.set_limit(0)
    assert not throttler.is_active(), "Should be inactive when unlimited"
    print("✓ User-space throttler can be disabled")


def test_rate_update():
    """Test dynamic rate updates."""
    throttler = TokenBucketThrottler(rate_bytes_per_sec=1024)
    
    # Consume some tokens
    throttler.consume(512)
    
    # Update rate
    throttler.set_rate(2048)
    
    # Should use new rate
    stats = throttler.get_stats()
    assert stats['rate_bytes_per_sec'] == 2048, "Rate should be updated"
    print("✓ Rate updates work correctly")


if __name__ == "__main__":
    print("Testing User-Space Throttler...")
    print()
    
    test_token_bucket_basic()
    test_token_bucket_unlimited()
    test_user_space_throttler()
    test_rate_update()
    
    print()
    print("✅ All tests passed!")
