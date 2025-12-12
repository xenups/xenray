"""Core types and enums."""
from enum import Enum


class ConnectionMode(Enum):
    """Connection modes."""

    PROXY = "proxy"
    VPN = "vpn"

    def __str__(self):
        return self.value
