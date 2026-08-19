"""Windows OS-abstraction implementations.

One component per file (SRP):
    tun_dns.py    → WindowsTunDnsConfigurator (ITunDnsConfigurator)
    network.py    → WindowsNetworkAdapter (INetworkAdapter)
    settings.py   → WindowsSystemSettingsAdapter (ISystemSettingsAdapter)
    process.py    → WindowsProcessAdapter (IProcessAdapter)
    firewall.py   → WindowsFirewallAdapter (IFirewallAdapter)
"""

from __future__ import annotations

from src.platform.windows.firewall import WindowsFirewallAdapter
from src.platform.windows.network import WindowsNetworkAdapter
from src.platform.windows.process import WindowsProcessAdapter
from src.platform.windows.settings import WindowsSystemSettingsAdapter
from src.platform.windows.tun_dns import WindowsTunDnsConfigurator

__all__ = [
    "WindowsTunDnsConfigurator",
    "WindowsNetworkAdapter",
    "WindowsSystemSettingsAdapter",
    "WindowsProcessAdapter",
    "WindowsFirewallAdapter",
]
