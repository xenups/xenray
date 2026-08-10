"""Route Manager Service.

Owns all OS-level routing-table mutations for a single TUN session:
- Static host routes for proxy-server endpoint bypass (Wintun loop break)
- CIDR routes for LAN-sharing bypass (so LAN-device packets skip the TUN)
- DNS resolution of proxy hostnames with thread-safe per-call timeouts

This service is stateful per TUN session: it records every route it adds
so that ``cleanup_routes`` can undo them precisely on teardown.

Design rules:
- No sing-box JSON config logic.
- No process spawning.
- No registry access.
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
import subprocess
from typing import List, Union

from src.core.constants import LAN_PRIVATE_RANGES
from src.core.logger import logger
from src.utils.platform_utils import PlatformUtils

# Per-call DNS resolution timeout — avoids blocking the caller thread
# indefinitely for unreachable or slow DNS servers.
_DNS_RESOLUTION_TIMEOUT = 5.0  # seconds


class RouteManagerService:
    """Manages OS static routes for a single TUN session.

    Lifecycle::

        mgr = RouteManagerService()
        mgr.setup_routes(bypass_endpoints=["proxy.example.com"], gateway="192.168.1.1")
        # ... sing-box runs ...
        mgr.cleanup_routes()  # removes everything that was added

    The internal ``_added_routes`` and ``_added_lan_routes`` lists record
    exactly what was added so cleanup is precise even after partial failures.
    """

    def __init__(self) -> None:
        self._added_routes: List[str] = []       # individual host /32 routes
        self._added_lan_routes: List[str] = []   # CIDR network routes (LAN sharing)

    # ------------------------------------------------------------------
    # High-level API called by SingboxService
    # ------------------------------------------------------------------

    def setup_routes(
        self,
        bypass_endpoints: Union[str, List[str]],
        gateway: str,
        allow_lan: bool = False,
    ) -> None:
        """Add all necessary static routes for a TUN session.

        Args:
            bypass_endpoints: Proxy server hostnames / IPs that must bypass
                the TUN so sing-box can reach Xray without a routing loop.
            gateway: Physical-adapter default gateway IP.
            allow_lan: When True, add CIDR routes for all private LAN ranges
                so LAN-device packets bypass the TUN (LAN proxy sharing).
        """
        if not gateway:
            logger.warning("[RouteManagerService] No gateway — route bypass may be incomplete.")
            return

        resolved = self.resolve_ips(bypass_endpoints if isinstance(bypass_endpoints, list) else [bypass_endpoints])
        for ip in resolved:
            self.add_static_route(ip, gateway)

        if allow_lan:
            self.add_lan_routes(gateway)

    def cleanup_routes(self) -> None:
        """Remove every route added during this session (host + CIDR)."""
        self._cleanup_host_routes()
        self._cleanup_lan_routes()

    # ------------------------------------------------------------------
    # Host-route helpers
    # ------------------------------------------------------------------

    def resolve_ips(self, endpoints: List[str]) -> List[str]:
        """Resolve domain names to IPv4 addresses with per-call timeout.

        Already-IP endpoints are passed through unchanged.  Uses
        ``ThreadPoolExecutor`` so ``socket.setdefaulttimeout()`` is never
        called (global-state mutation avoided).

        Returns:
            Deduplicated list of resolved IPv4 strings.
        """
        resolved_ips: List[str] = []

        for ep in endpoints:
            ep = ep.strip()
            if not ep:
                continue

            # Already an IP — no resolution needed.
            try:
                ipaddress.ip_address(ep)
                resolved_ips.append(ep)
                continue
            except (ValueError, ipaddress.AddressValueError):
                pass

            try:
                logger.info(f"[RouteManagerService] Resolving {ep}...")

                def _do_resolve(domain: str) -> List[str]:
                    addrs = socket.getaddrinfo(domain, None, socket.AF_INET)
                    return list({info[4][0] for info in addrs})

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_do_resolve, ep)
                    ips = future.result(timeout=_DNS_RESOLUTION_TIMEOUT)

                logger.info(f"[RouteManagerService] Resolved {ep} → {ips}")
                resolved_ips.extend(ips)

            except concurrent.futures.TimeoutError:
                logger.warning(f"[RouteManagerService] DNS resolution timed out for {ep}")
            except (socket.gaierror, OSError) as exc:
                logger.warning(f"[RouteManagerService] Failed to resolve {ep}: {exc}")

        return list(set(resolved_ips))

    def add_static_route(self, ip: str, gateway: str) -> None:
        """Add a /32 host route for ``ip`` via ``gateway``.

        Private/reserved IPs are silently skipped — routing them via the
        physical gateway would either be a no-op (same subnet) or, worse,
        leak ISP-hijacked DNS responses off the encrypted tunnel.
        """
        if ip in self._added_routes:
            return

        if self.is_private_or_reserved(ip):
            logger.debug(f"[RouteManagerService] Skipping private/reserved IP: {ip}")
            return

        cmd = self._host_route_add_cmd(ip, gateway)
        try:
            logger.info(f"[RouteManagerService] Adding static route: {ip} → {gateway}")
            subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            self._added_routes.append(ip)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error(f"[RouteManagerService] Failed to add route for {ip}: {exc}")

    def _cleanup_host_routes(self) -> None:
        """Remove all /32 host routes added during this session."""
        platform = PlatformUtils.get_platform()
        for ip in self._added_routes[:]:
            try:
                cmd = self._host_route_del_cmd(ip, platform)
                logger.debug(f"[RouteManagerService] Removing static route: {ip}")
                subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    creationflags=PlatformUtils.get_subprocess_flags(),
                    startupinfo=PlatformUtils.get_startupinfo(),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                logger.warning(f"[RouteManagerService] Failed to remove route for {ip}: {exc}")
            finally:
                if ip in self._added_routes:
                    self._added_routes.remove(ip)

    # ------------------------------------------------------------------
    # LAN CIDR-route helpers
    # ------------------------------------------------------------------

    def add_lan_routes(self, gateway: str) -> None:
        """Add CIDR routes for all private LAN ranges via ``gateway``.

        Required for LAN proxy sharing: without these, packets from LAN
        clients would enter the TUN and be looped back through the tunnel
        instead of reaching the physical LAN interface.
        """
        for cidr in LAN_PRIVATE_RANGES:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                logger.warning(f"[RouteManagerService] Skipping invalid LAN range: {cidr}")
                continue
            self._add_cidr_route(network, gateway)

    def _add_cidr_route(self, network: ipaddress.IPv4Network, gateway: str) -> None:
        """Add a network-level CIDR route via the physical gateway."""
        key = str(network)
        if key in self._added_lan_routes:
            return

        cmd = self._cidr_route_add_cmd(network, gateway)
        try:
            logger.info(f"[RouteManagerService] Adding LAN route: {network} → {gateway}")
            subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            self._added_lan_routes.append(key)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error(f"[RouteManagerService] Failed to add LAN route {network}: {exc}")

    def _cleanup_lan_routes(self) -> None:
        """Remove all CIDR routes added during this session."""
        platform = PlatformUtils.get_platform()
        for key in self._added_lan_routes[:]:
            try:
                network = ipaddress.ip_network(key, strict=False)
                cmd = self._cidr_route_del_cmd(network, platform)
                logger.debug(f"[RouteManagerService] Removing LAN route: {key}")
                subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    creationflags=PlatformUtils.get_subprocess_flags(),
                    startupinfo=PlatformUtils.get_startupinfo(),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                logger.warning(f"[RouteManagerService] Failed to remove LAN route {key}: {exc}")
            finally:
                if key in self._added_lan_routes:
                    self._added_lan_routes.remove(key)

    # ------------------------------------------------------------------
    # Platform-specific command builders (pure functions — no side effects)
    # ------------------------------------------------------------------

    @staticmethod
    def _host_route_add_cmd(ip: str, gateway: str) -> List[str]:
        platform = PlatformUtils.get_platform()
        if platform == "windows":
            return ["route", "add", ip, "mask", "255.255.255.255", gateway, "metric", "1"]
        if platform == "macos":
            return ["route", "-n", "add", "-host", ip, gateway]
        return ["ip", "route", "add", ip, "via", gateway]  # Linux

    @staticmethod
    def _host_route_del_cmd(ip: str, platform: str) -> List[str]:
        if platform == "windows":
            return ["route", "delete", ip]
        if platform == "macos":
            return ["route", "-n", "delete", "-host", ip]
        return ["ip", "route", "del", ip]  # Linux

    @staticmethod
    def _cidr_route_add_cmd(network: ipaddress.IPv4Network, gateway: str) -> List[str]:
        platform = PlatformUtils.get_platform()
        if platform == "windows":
            return [
                "route", "add",
                str(network.network_address), "mask", str(network.netmask),
                gateway, "metric", "1",
            ]
        if platform == "macos":
            return ["route", "-n", "add", "-net", str(network), gateway]
        return ["ip", "route", "add", str(network), "via", gateway]  # Linux

    @staticmethod
    def _cidr_route_del_cmd(network: ipaddress.IPv4Network, platform: str) -> List[str]:
        if platform == "windows":
            return ["route", "delete", str(network.network_address)]
        if platform == "macos":
            return ["route", "-n", "delete", "-net", str(network)]
        return ["ip", "route", "del", str(network)]  # Linux

    # ------------------------------------------------------------------
    # Static classification helper
    # ------------------------------------------------------------------

    @staticmethod
    def is_private_or_reserved(ip: str) -> bool:
        """Return True if ``ip`` is in private/reserved IPv4 space.

        Covers RFC 1918 (10/8, 172.16/12, 192.168/16), loopback (127/8),
        link-local (169.254/16), CGNAT (100.64/10) and other IANA-reserved
        blocks.  Invalid strings are treated as reserved (safe default).
        """
        try:
            return bool(ipaddress.ip_address(ip).is_private)
        except ValueError:
            return True
