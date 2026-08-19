"""Route Manager Service — High-level routing orchestrator for TUN sessions."""

from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
from typing import List, Optional, Union

from src.core.constants import LAN_PRIVATE_RANGES
from src.core.logger import logger
from src.platform.factory import get_route_adapter
from src.platform.interfaces.route import IRouteAdapter

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

    Tracks added host routes and LAN CIDR routes per session and delegates
    actual OS routing table modifications to the platform-specific IRouteAdapter.
    """

    def __init__(self, route_adapter: Optional[IRouteAdapter] = None) -> None:
        self._route_adapter: IRouteAdapter = route_adapter or get_route_adapter()
        self._added_routes: List[str] = []  # individual host /32 routes
        self._added_lan_routes: List[str] = []  # CIDR network routes (LAN sharing)

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

        Already-IP endpoints are passed through unchanged. Uses
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
        physical gateway would either be a no-op (same subnet) or leak
        ISP-hijacked DNS responses off the encrypted tunnel.
        """
        if ip in self._added_routes:
            return

        if self.is_private_or_reserved(ip):
            logger.debug(f"[RouteManagerService] Skipping private/reserved IP: {ip}")
            return

        if self._route_adapter.add_host_route(ip, gateway):
            self._added_routes.append(ip)
        else:
            logger.error(f"[RouteManagerService] Failed to add route for {ip} via {gateway}")

    def _cleanup_host_routes(self) -> None:
        """Remove all /32 host routes added during this session.

        Idempotent & crash-safe: only drops an entry when the delete succeeded,
        so a failed OS removal keeps tracking for retry on the next call.
        """
        remaining = []
        for ip in self._added_routes:
            if self._route_adapter.delete_host_route(ip):
                logger.debug(f"[RouteManagerService] Removed static route: {ip}")
            else:
                logger.warning(f"[RouteManagerService] Route delete for {ip} failed — keeping for retry")
                remaining.append(ip)
        self._added_routes = remaining

    # ------------------------------------------------------------------
    # LAN CIDR-route helpers
    # ------------------------------------------------------------------

    def add_lan_routes(self, gateway: str) -> None:
        """Add CIDR routes for all private LAN ranges via ``gateway``."""
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

        if self._route_adapter.add_cidr_route(network, gateway):
            self._added_lan_routes.append(key)
        else:
            logger.error(f"[RouteManagerService] Failed to add LAN route {network} via {gateway}")

    def _cleanup_lan_routes(self) -> None:
        """Remove all CIDR routes added during this session.

        Idempotent & crash-safe: only drops an entry when deletion succeeded.
        """
        remaining = []
        for key in self._added_lan_routes:
            try:
                network = ipaddress.ip_network(key, strict=False)
                if self._route_adapter.delete_cidr_route(network):
                    logger.debug(f"[RouteManagerService] Removed LAN route: {key}")
                else:
                    logger.warning(f"[RouteManagerService] LAN route delete for {key} failed — keeping for retry")
                    remaining.append(key)
            except (ValueError, Exception) as exc:
                logger.warning(f"[RouteManagerService] Error deleting LAN route {key}: {exc}")
                remaining.append(key)
        self._added_lan_routes = remaining

    # ------------------------------------------------------------------
    # Static classification helper
    # ------------------------------------------------------------------

    @staticmethod
    def is_private_or_reserved(ip: str) -> bool:
        """Return True if ``ip`` is in private/reserved IPv4 space.

        Covers RFC 1918 (10/8, 172.16/12, 192.168/16), loopback (127/8),
        link-local (169.254/16), CGNAT (100.64/10) and other IANA-reserved
        blocks. Invalid strings are treated as reserved (safe default).
        """
        try:
            return bool(ipaddress.ip_address(ip).is_private)
        except ValueError:
            return True


__all__ = ["RouteManagerService"]
