"""
Traffic shaping utilities for TUN interface bandwidth control.

Provides platform-specific implementations for enforcing throughput limits.
"""

import subprocess
from typing import Optional

from loguru import logger

from src.utils.platform_utils import PlatformUtils
from src.utils.user_space_throttler import UserSpaceThrottler


class TrafficShaper:
    """
    Platform-specific traffic shaping for TUN interfaces.
    
    Supports:
    - Linux: tc (traffic control) with HTB qdisc
    - Windows: netsh QoS policies
    - macOS: dnctl pipes
    """
    
    def __init__(self, interface_name: Optional[str] = None):
        """
        Initialize traffic shaper.
        
        Args:
            interface_name: TUN interface name (auto-detected if None)
        """
        self._interface = interface_name or self._get_tun_interface()
        self._platform = PlatformUtils.get_platform()
        self._last_limit = 0
        
        # Initialize user-space fallback throttler
        self._fallback_throttler = UserSpaceThrottler()
        self._using_fallback = False
        
    def _get_tun_interface(self) -> str:
        """Get TUN interface name based on platform."""
        return PlatformUtils.get_tun_interface_name()
    
    def apply_limit(self, limit_bytes_per_sec: int) -> bool:
        """
        Apply bandwidth limit to TUN interface.
        
        Args:
            limit_bytes_per_sec: Bandwidth limit in bytes/sec (0 = unlimited)
            
        Returns:
            True if limit was applied successfully, False otherwise
        """
        if limit_bytes_per_sec == self._last_limit:
            return True  # No change needed
            
        limit_str = "Unlimited" if limit_bytes_per_sec == 0 else f"{limit_bytes_per_sec/1024:.1f} KB/s"
        logger.info(f"[TrafficShaper] Applying {limit_str} to {self._interface}")
        
        try:
            # Try platform-specific traffic shaping first
            platform_success = False
            
            if self._platform == "linux":
                platform_success = self._apply_linux_tc(limit_bytes_per_sec)
            elif self._platform == "windows":
                platform_success = self._apply_windows_qos(limit_bytes_per_sec)
            elif self._platform == "macos":
                platform_success = self._apply_macos_dnctl(limit_bytes_per_sec)
            else:
                logger.warning(f"[TrafficShaper] Unsupported platform: {self._platform}")
            
            # If platform shaping failed, use user-space fallback
            if not platform_success:
                logger.info(f"[TrafficShaper] Platform shaping unavailable, using user-space fallback")
                fallback_success = self._fallback_throttler.set_limit(limit_bytes_per_sec)
                
                if fallback_success:
                    self._using_fallback = True
                    self._last_limit = limit_bytes_per_sec
                    logger.info(f"[TrafficShaper] Fallback throttler active: {limit_str} (advisory)")
                    return True
                else:
                    logger.error(f"[TrafficShaper] Both platform and fallback throttling failed")
                    return False
            else:
                # Platform shaping succeeded
                self._using_fallback = False
                self._last_limit = limit_bytes_per_sec
                logger.info(f"[TrafficShaper] Platform shaping active: {limit_str}")
                return True
            
        except Exception as e:
            logger.error(f"[TrafficShaper] Failed to apply limit: {e}")
            return False
    
    def _apply_linux_tc(self, limit_bytes: int) -> bool:
        """Apply traffic control using Linux tc command."""
        if not self._interface:
            return False
            
        try:
            # Remove existing qdisc
            subprocess.run(
                ["tc", "qdisc", "del", "dev", self._interface, "root"],
                capture_output=True,
                check=False  # Don't fail if no qdisc exists
            )
            
            if limit_bytes == 0:
                # Unlimited - use default pfifo_fast
                return True
                
            # Add HTB (Hierarchical Token Bucket) qdisc with limit
            # Convert bytes/sec to kbit/sec for tc
            limit_kbit = int((limit_bytes * 8) / 1000)
            
            # Add root qdisc
            result = subprocess.run(
                ["tc", "qdisc", "add", "dev", self._interface, "root", "handle", "1:", "htb", "default", "10"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"[TrafficShaper] tc qdisc add failed: {result.stderr}")
                return False
            
            # Add class with rate limit
            result = subprocess.run(
                ["tc", "class", "add", "dev", self._interface, "parent", "1:", "classid", "1:10", "htb", "rate", f"{limit_kbit}kbit"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"[TrafficShaper] tc class add failed: {result.stderr}")
                return False
                
            logger.debug(f"[TrafficShaper] Linux tc applied: {limit_kbit}kbit/s")
            return True
            
        except FileNotFoundError:
            logger.warning("[TrafficShaper] tc command not found - install iproute2")
            return False
        except Exception as e:
            logger.error(f"[TrafficShaper] Linux tc error: {e}")
            return False
    
    def _apply_windows_qos(self, limit_bytes: int) -> bool:
        """Apply QoS policy using Windows netsh command."""
        if not self._interface:
            return False
            
        try:
            # Remove existing policy
            subprocess.run(
                ["netsh", "qos", "policy", "delete", "name=XenRayTunLimit"],
                capture_output=True,
                check=False,
                creationflags=PlatformUtils.get_subprocess_flags()
            )
            
            if limit_bytes == 0:
                # Unlimited - policy removed
                return True
            
            # Convert bytes/sec to throttle rate (percentage is complex, use absolute)
            # Windows QoS uses throttle rate in bytes/sec
            limit_kbps = int((limit_bytes * 8) / 1000)
            
            # Add QoS policy for TUN interface
            result = subprocess.run(
                [
                    "netsh", "qos", "policy", "add",
                    "name=XenRayTunLimit",
                    f"interface={self._interface}",
                    f"throttleRate={limit_kbps}kbps"
                ],
                capture_output=True,
                text=True,
                creationflags=PlatformUtils.get_subprocess_flags()
            )
            
            if result.returncode != 0:
                logger.error(f"[TrafficShaper] netsh qos failed: {result.stderr}")
                return False
                
            logger.debug(f"[TrafficShaper] Windows QoS applied: {limit_kbps}kbps")
            return True
            
        except FileNotFoundError:
            logger.warning("[TrafficShaper] netsh command not found")
            return False
        except Exception as e:
            logger.error(f"[TrafficShaper] Windows QoS error: {e}")
            return False
    
    def _apply_macos_dnctl(self, limit_bytes: int) -> bool:
        """Apply traffic control using macOS dnctl command."""
        if not self._interface:
            return False
            
        try:
            # Remove existing pipe
            subprocess.run(
                ["dnctl", "pipe", "delete", "1"],
                capture_output=True,
                check=False
            )
            
            if limit_bytes == 0:
                # Unlimited - pipe removed
                return True
            
            # Convert bytes/sec to bits/sec for dnctl
            limit_bps = limit_bytes * 8
            
            # Add dnctl pipe with bandwidth limit
            result = subprocess.run(
                ["dnctl", "pipe", "1", "config", "bw", f"{limit_bps}bit/s"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"[TrafficShaper] dnctl pipe config failed: {result.stderr}")
                return False
            
            # Apply pipe to interface (requires pfctl rules - simplified)
            logger.debug(f"[TrafficShaper] macOS dnctl pipe configured: {limit_bps}bps")
            logger.warning("[TrafficShaper] macOS: dnctl pipe created but pfctl rules not applied (requires manual setup)")
            return True
            
        except FileNotFoundError:
            logger.warning("[TrafficShaper] dnctl command not found")
            return False
        except Exception as e:
            logger.error(f"[TrafficShaper] macOS dnctl error: {e}")
            return False
    
    def remove_limits(self) -> bool:
        """Remove all traffic shaping limits."""
        return self.apply_limit(0)
    
    def get_throttler(self) -> UserSpaceThrottler:
        """Get the fallback user-space throttler instance."""
        return self._fallback_throttler
    
    def is_using_fallback(self) -> bool:
        """Check if currently using fallback throttler."""
        return self._using_fallback
