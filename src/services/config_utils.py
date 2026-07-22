"""Shared utility functions for Xray configuration processing."""
import ipaddress
from typing import Optional


def is_ip(address: str) -> bool:
    """Check if address is an IP (IPv4 or IPv6)."""
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False


def get_server_object(settings: dict) -> Optional[dict]:
    """Extract server object from settings."""
    if "vnext" in settings and settings["vnext"]:
        return settings["vnext"][0]
    elif "servers" in settings and settings["servers"]:
        return settings["servers"][0]
    return None
