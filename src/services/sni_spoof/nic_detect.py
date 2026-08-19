"""Systematic physical-NIC detection helper facade.

Delegates directly to WindowsNetworkAdapter in src.platform.windows.network.
"""

from __future__ import annotations

from src.platform.windows.network import (
    IF_TYPE_ETHERNET_CSMACD,
    IF_TYPE_IEEE80211,
    IF_TYPE_TUNNEL,
    _is_physical_iftype,
    get_physical_nic_candidates,
)

__all__ = [
    "IF_TYPE_ETHERNET_CSMACD",
    "IF_TYPE_IEEE80211",
    "IF_TYPE_TUNNEL",
    "_is_physical_iftype",
    "get_physical_nic_candidates",
]
