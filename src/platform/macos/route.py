"""macOS Routing Table Adapter using route command."""

from __future__ import annotations

import ipaddress
import subprocess
from typing import List

from loguru import logger

from src.platform.constants import CMD_ROUTE
from src.platform.interfaces.route import IRouteAdapter


class MacosRouteAdapter(IRouteAdapter):
    """macOS route -n implementation for host and CIDR routes."""

    def _run(self, cmd: List[str]) -> bool:
        try:
            res = subprocess.run(cmd, check=False, capture_output=True)
            if hasattr(res, "returncode") and isinstance(res.returncode, int):
                return res.returncode == 0
            return True
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error(f"[MacosRouteAdapter] Command failed {' '.join(cmd)}: {exc}")
            return False

    def add_host_route(self, ip: str, gateway: str) -> bool:
        """Add /32 host route via gateway using route -n add -host."""
        cmd = [CMD_ROUTE, "-n", "add", "-host", ip, gateway]
        logger.info(f"[MacosRouteAdapter] Adding host route: {ip} → {gateway}")
        return self._run(cmd)

    def delete_host_route(self, ip: str) -> bool:
        """Delete host route using route -n delete -host."""
        cmd = [CMD_ROUTE, "-n", "delete", "-host", ip]
        logger.debug(f"[MacosRouteAdapter] Deleting host route: {ip}")
        return self._run(cmd)

    def add_cidr_route(self, network: ipaddress.IPv4Network, gateway: str) -> bool:
        """Add network CIDR route via gateway using route -n add -net."""
        cmd = [CMD_ROUTE, "-n", "add", "-net", str(network), gateway]
        logger.info(f"[MacosRouteAdapter] Adding CIDR route: {network} → {gateway}")
        return self._run(cmd)

    def delete_cidr_route(self, network: ipaddress.IPv4Network) -> bool:
        """Delete network CIDR route using route -n delete -net."""
        cmd = [CMD_ROUTE, "-n", "delete", "-net", str(network)]
        logger.debug(f"[MacosRouteAdapter] Deleting CIDR route: {network}")
        return self._run(cmd)


__all__ = ["MacosRouteAdapter"]
