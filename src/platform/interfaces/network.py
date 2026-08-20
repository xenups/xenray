"""Network interface and NIC discovery abstraction contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class INetworkAdapter(ABC):
    """Physical-NIC discovery: IP + DNS, no name blacklists or IP heuristics."""

    @abstractmethod
    def get_physical_nic_candidates(self) -> list[dict]:
        """Physical, up, gateway-bearing adapters: [{"name","ip","iftype",
        "operstatus","gateway"}]. Empty when none/unavailable."""

    @abstractmethod
    def get_physical_lan_ip(self) -> Optional[str]:
        """Primary physical LAN IPv4, or None if unavailable (never fabricated)."""

    @abstractmethod
    def get_system_dns_servers(self) -> list[str]:
        """System DNS servers (physical adapters only)."""

    @abstractmethod
    def get_primary_interface(self):
        """(name, ip, subnet, gateway) of the default-route interface."""

    @abstractmethod
    def ping_mtu(self, host: str, payload_size: int, timeout: int) -> bool:
        """Ping host with Don't Fragment (DF) flag set for the given payload size."""
