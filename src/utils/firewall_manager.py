"""FirewallManager - facade over the OS firewall abstraction.

The actual firewall commands live in the platform adapters (e.g. WindowsFirewallAdapter).
This class provides the stable public API used by the UI/controllers and delegates directly
to the platform factory without manual platform checks or magic number port calculations.
"""

from __future__ import annotations

from typing import List, Optional, Union

from src.core.constants import LAN_FIREWALL_RULE_NAME
from src.platform.factory import get_firewall_adapter


class FirewallManager:
    """Manage the host firewall inbound rule for LAN sharing."""

    RULE_NAME = LAN_FIREWALL_RULE_NAME

    @staticmethod
    def check_lan_firewall_rule() -> bool:
        """Return True if the inbound rule already exists."""
        return get_firewall_adapter().check_lan_firewall_rule()

    @staticmethod
    def add_lan_firewall_rule(ports: List[int]) -> bool:
        """Create the inbound allow rule for the given ports (elevated)."""
        return get_firewall_adapter().add_lan_firewall_rule(ports)

    @staticmethod
    def allow_lan_sharing_ports(socks_port: Union[int, List[int]], http_port: Optional[int] = None) -> bool:
        """Create inbound firewall rules for explicit SOCKS and HTTP ports without magic offset calculations."""
        ports: List[int] = []
        if isinstance(socks_port, int) and socks_port > 0:
            ports.append(socks_port)
        elif isinstance(socks_port, list):
            ports.extend(p for p in socks_port if isinstance(p, int) and p > 0)

        if isinstance(http_port, int) and http_port > 0:
            ports.append(http_port)

        if not ports:
            return False
        return get_firewall_adapter().add_lan_firewall_rule(ports)

    @staticmethod
    def remove_lan_firewall_rule() -> None:
        """Remove the inbound allow rule created by XenRay."""
        get_firewall_adapter().remove_lan_firewall_rule()


__all__ = ["FirewallManager"]
