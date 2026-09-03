"""Network interface utilities (compat facade).

Physical-NIC / LAN-IP discovery now lives in the platform adapters (IP Helper
API-backed ``WindowsNetworkAdapter`` in ``src.platform.windows.network``).
``NetworkInterfaceDetector`` is kept as a thin, lazy facade so existing
callers keep working; new code should use
``src.platform.factory.get_network_adapter()`` directly.
"""

from __future__ import annotations

from typing import Optional, Tuple

# Constants
ROUTE_COMMAND_TIMEOUT = 5  # seconds
IPCONFIG_COMMAND_TIMEOUT = 5  # seconds


class NetworkInterfaceDetector:
    """Detects primary network interface on Windows (delegates to adapter)."""

    @staticmethod
    def get_primary_interface() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Get primary network interface details.

        Returns:
            Tuple of (interface_name, interface_ip, subnet, gateway)
            e.g., ("Wi-Fi", "192.168.1.10", "192.168.1.0/24", "192.168.1.1")
        """
        from src.platform.factory import get_network_adapter

        return get_network_adapter().get_primary_interface()

    @staticmethod
    def get_primary_lan_ip() -> Optional[str]:
        """Discover the host's primary LAN IPv4 address.

        Systemic only: physical, up, gateway-bearing adapters from the Windows
        IP Helper API (``nic_detect``) first, then the OS default-route egress.
        No adapter-name blacklists, no IP-prefix heuristics. Returns ``None``
        when no usable interface exists (never a fabricated address).
        """
        from src.platform.factory import get_network_adapter

        return get_network_adapter().get_physical_lan_ip()
