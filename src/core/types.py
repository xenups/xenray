"""Core types and enums."""
from enum import Enum


class ConnectionMode(Enum):
    """Connection modes."""

    PROXY = "proxy"
    VPN = "vpn"

    def __str__(self):
        return self.value


class TunEngine(Enum):
    """TUN engine implementation options."""

    SING_BOX = "sing-box"
    XRAY = "xray"

    def __str__(self):
        return self.value
