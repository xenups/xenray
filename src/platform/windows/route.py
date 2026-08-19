"""Windows Routing Table Adapter using route.exe."""

from __future__ import annotations

import ipaddress
import subprocess
from typing import List

from loguru import logger

from src.platform.constants import CMD_ROUTE
from src.platform.factory import get_process_adapter
from src.platform.interfaces.route import IRouteAdapter


class WindowsRouteAdapter(IRouteAdapter):
    """Windows route.exe implementation for host and CIDR routes."""

    def _run(self, cmd: List[str]) -> bool:
        try:
            res = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                creationflags=get_process_adapter().get_subprocess_flags(),
                startupinfo=get_process_adapter().get_startupinfo(),
            )
            if hasattr(res, "returncode") and isinstance(res.returncode, int):
                return res.returncode == 0
            return True
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error(f"[WindowsRouteAdapter] Command failed {' '.join(cmd)}: {exc}")
            return False

    def add_host_route(self, ip: str, gateway: str) -> bool:
        """Add /32 host route via gateway using route.exe."""
        cmd = [CMD_ROUTE, "add", ip, "mask", "255.255.255.255", gateway, "metric", "1"]
        logger.info(f"[WindowsRouteAdapter] Adding host route: {ip} → {gateway}")
        return self._run(cmd)

    def delete_host_route(self, ip: str) -> bool:
        """Delete host route using route.exe."""
        cmd = [CMD_ROUTE, "delete", ip]
        logger.debug(f"[WindowsRouteAdapter] Deleting host route: {ip}")
        return self._run(cmd)

    def add_cidr_route(self, network: ipaddress.IPv4Network, gateway: str) -> bool:
        """Add network CIDR route via gateway using route.exe."""
        cmd = [
            CMD_ROUTE,
            "add",
            str(network.network_address),
            "mask",
            str(network.netmask),
            gateway,
            "metric",
            "1",
        ]
        logger.info(f"[WindowsRouteAdapter] Adding CIDR route: {network} → {gateway}")
        return self._run(cmd)

    def delete_cidr_route(self, network: ipaddress.IPv4Network) -> bool:
        """Delete network CIDR route using route.exe."""
        cmd = [CMD_ROUTE, "delete", str(network.network_address)]
        logger.debug(f"[WindowsRouteAdapter] Deleting CIDR route: {network}")
        return self._run(cmd)


__all__ = ["WindowsRouteAdapter"]
