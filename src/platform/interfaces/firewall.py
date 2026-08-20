"""Host firewall rules abstraction contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional


class IFirewallAdapter(ABC):
    """Host firewall rule management (LAN sharing allow rules)."""

    @abstractmethod
    def add_rule(self, name: str, port: int, interface: Optional[str] = None) -> bool:
        """Add an inbound allow rule for *port*."""

    @abstractmethod
    def remove_rule(self, name: str) -> bool:
        """Remove the rule named *name*."""

    @abstractmethod
    def check_lan_firewall_rule(self) -> bool:
        """Check if the LAN sharing inbound allow rule exists."""

    @abstractmethod
    def add_lan_firewall_rule(self, ports: List[int]) -> bool:
        """Create the LAN sharing inbound allow rule for the given ports."""

    @abstractmethod
    def remove_lan_firewall_rule(self) -> None:
        """Remove the LAN sharing inbound allow rule."""
