"""Routing table abstraction interface."""

from __future__ import annotations

import ipaddress
from abc import ABC, abstractmethod


class IRouteAdapter(ABC):
    """Abstraction for platform-specific OS routing table manipulations."""

    @abstractmethod
    def add_host_route(self, ip: str, gateway: str) -> bool:
        """Add /32 host route via gateway."""
        pass

    @abstractmethod
    def delete_host_route(self, ip: str) -> bool:
        """Delete host route."""
        pass

    @abstractmethod
    def add_cidr_route(self, network: ipaddress.IPv4Network, gateway: str) -> bool:
        """Add network CIDR route via gateway."""
        pass

    @abstractmethod
    def delete_cidr_route(self, network: ipaddress.IPv4Network) -> bool:
        """Delete network CIDR route."""
        pass
