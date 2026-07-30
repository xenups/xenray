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
                from src.utils.network_interface import NetworkInterfaceDetector

                _, _, _, gateway = NetworkInterfaceDetector.get_primary_interface()
                if gateway:
                    return gateway

                result = subprocess.run(
                    ["route", "print", "0.0.0.0"],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                candidates = []
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 4 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                        gw = parts[2]
                        if NetworkInterfaceDetector._is_valid_ip(gw):
                            metric = int(parts[4]) if len(parts) >= 5 and parts[4].isdigit() else 9999
                            candidates.append((metric, gw))
                if candidates:
                    candidates.sort(key=lambda x: x[0])
                    return candidates[0][1]

            elif system == "Darwin":  # macOS
                result = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True)
                for line in result.stdout.splitlines():
                    if "gateway:" in line:
                        return line.split(":")[1].strip()

            else:  # Linux
                result = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True)
                for line in result.stdout.splitlines():
                    if "default" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            return parts[2]

        except Exception as e:
            logger.debug(f"[NetworkValidator] Error getting gateway: {e}")

        return None
