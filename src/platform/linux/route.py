"""Linux Routing Table Adapter using ip route command."""

from __future__ import annotations

import ipaddress
import subprocess
from typing import List

from loguru import logger

from src.platform.constants import CMD_IP
from src.platform.interfaces.route import IRouteAdapter


class LinuxRouteAdapter(IRouteAdapter):
    """Linux ip route implementation for host and CIDR routes."""

    def _run(self, cmd: List[str]) -> bool:
        try:
            res = subprocess.run(cmd, check=False, capture_output=True)
            if hasattr(res, "returncode") and isinstance(res.returncode, int):
                return res.returncode == 0
            return True
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error(f"[LinuxRouteAdapter] Command failed {' '.join(cmd)}: {exc}")
            return False

    def add_host_route(self, ip: str, gateway: str) -> bool:
        """Add /32 host route via gateway using ip route add."""
        cmd = [CMD_IP, "route", "add", ip, "via", gateway]
        logger.info(f"[LinuxRouteAdapter] Adding host route: {ip} → {gateway}")
        return self._run(cmd)

    def delete_host_route(self, ip: str) -> bool:
        """Delete host route using ip route del."""
        cmd = [CMD_IP, "route", "del", ip]
        logger.debug(f"[LinuxRouteAdapter] Deleting host route: {ip}")
        return self._run(cmd)

    def add_cidr_route(self, network: ipaddress.IPv4Network, gateway: str) -> bool:
        """Add network CIDR route via gateway using ip route add."""
        cmd = [CMD_IP, "route", "add", str(network), "via", gateway]
        logger.info(f"[LinuxRouteAdapter] Adding CIDR route: {network} → {gateway}")
        return self._run(cmd)

    def delete_cidr_route(self, network: ipaddress.IPv4Network) -> bool:
        """Delete network CIDR route using ip route del."""
        cmd = [CMD_IP, "route", "del", str(network)]
        logger.debug(f"[LinuxRouteAdapter] Deleting CIDR route: {network}")
        return self._run(cmd)


__all__ = ["LinuxRouteAdapter"]
