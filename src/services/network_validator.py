"""
Network validation service.

Handles network connectivity checks and validation.
"""

import socket
from typing import Optional

from loguru import logger


class NetworkValidator:
    """
    Validates network connectivity and configuration.
    
    Single Responsibility: Network validation only.
    """
    
    def check_internet_connection(self) -> bool:
        """
        Check if there is an active internet connection.
        
        Returns:
            True if internet is accessible, False otherwise
        """
        # Check if we have a default gateway
        gateway = self._get_default_gateway()
        if not gateway:
            logger.warning("[NetworkValidator] No default gateway found")
            return False
        
        # Check actual connectivity to high-availability hosts
        test_hosts = [
            ("8.8.8.8", 53),  # Google DNS
            ("1.1.1.1", 53),  # Cloudflare DNS
            ("208.67.222.222", 53),  # OpenDNS
        ]
        
        for host, port in test_hosts:
            try:
                s = socket.create_connection((host, port), timeout=3)
                s.close()
                logger.info(f"[NetworkValidator] Connection verified via {host}:{port}")
                return True
            except OSError:
                continue
        
        logger.error("[NetworkValidator] Failed to connect to any test host")
        return False
    
    def _get_default_gateway(self) -> Optional[str]:
        """
        Get the default gateway IP address.
        
        Returns:
            Gateway IP address or None if not found
        """
        import platform
        import subprocess
        
        try:
            system = platform.system()
            
            if system == "Windows":
                result = subprocess.run(
                    ["route", "print", "0.0.0.0"],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                for line in result.stdout.splitlines():
                    if "0.0.0.0" in line and "0.0.0.0" in line.split()[0]:
                        parts = line.split()
                        if len(parts) >= 3:
                            return parts[2]
            
            elif system == "Darwin":  # macOS
                result = subprocess.run(
                    ["route", "-n", "get", "default"],
                    capture_output=True,
                    text=True
                )
                for line in result.stdout.splitlines():
                    if "gateway:" in line:
                        return line.split(":")[1].strip()
            
            else:  # Linux
                result = subprocess.run(
                    ["ip", "route", "show", "default"],
                    capture_output=True,
                    text=True
                )
                for line in result.stdout.splitlines():
                    if "default" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            return parts[2]
        
        except Exception as e:
            logger.debug(f"[NetworkValidator] Error getting gateway: {e}")
        
        return None
