"""
Network validation service.

Handles network connectivity checks and validation.
"""

import socket
from typing import Optional

from loguru import logger

from src.core.constants import DNS_IP_CLOUDFLARE, DNS_IP_GOOGLE, DNS_IP_OPENDNS

# Per-host connect timeout (s) for the internet-connectivity probe.
CONNECT_TIMEOUT = 3
# DNS port used by the high-availability connectivity test hosts.
DNS_PORT = 53


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
            (DNS_IP_GOOGLE, DNS_PORT),
            (DNS_IP_CLOUDFLARE, DNS_PORT),
            (DNS_IP_OPENDNS, DNS_PORT),
        ]

        for host, port in test_hosts:
            try:
                s = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
                s.close()
                logger.info(f"[NetworkValidator] Connection verified via {host}:{port}")
                return True
            except OSError:
                continue

        logger.error("[NetworkValidator] Failed to connect to any test host")
        return False

    def _get_default_gateway(self) -> Optional[str]:
        """Get the default gateway IP address via Platform Network Adapter."""
        try:
            from src.platform.factory import get_network_adapter

            info = get_network_adapter().get_primary_interface()
            if info and len(info) >= 4 and info[3]:
                return info[3]
        except Exception as e:
            logger.debug(f"[NetworkValidator] Error getting gateway: {e}")

        return None
