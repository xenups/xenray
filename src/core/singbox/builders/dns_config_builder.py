"""Sing-box DNS configuration builder."""

from __future__ import annotations

import os
from typing import Optional

from src.core.constants import (
    DNS_IP_CLOUDFLARE,
    DNS_IP_CLOUDFLARE_ALT,
    DNS_IP_GOOGLE,
)


class DnsConfigBuilder:
    """Constructs the base sing-box 'dns' block."""

    def build(self, local_dns_server: Optional[str] = None) -> dict:
        """Build the base DNS configuration dict.

        Args:
            local_dns_server: Optional local DNS server IP/host. Defaults to env
                ``DNS_LOCAL_SERVER`` or Cloudflare Alt DNS.

        Returns:
            Dict containing the complete base sing-box DNS configuration.
        """
        dns_local = local_dns_server or os.getenv("DNS_LOCAL_SERVER", DNS_IP_CLOUDFLARE_ALT)

        return {
            "servers": [
                {
                    "tag": "bootstrap",
                    # DoH through the SOCKS proxy (tunneled path), NOT a bare
                    # direct UDP query to a foreign resolver: direct UDP to
                    # 8.8.8.8/1.1.1.1 is blocked/tampered on censored networks
                    # and caused recurring exchange failures.
                    "type": "https",
                    "server": DNS_IP_CLOUDFLARE,
                    "detour": "proxy",
                },
                {
                    "tag": "local_dns",
                    # Local/system DNS for DIRECT-routed domains (e.g. Iranian
                    # sites like ikco.ir). A LOCAL resolver (the router/gateway)
                    # is reachable without leaving the network.
                    "type": "udp",
                    "server": dns_local,
                    "detour": "direct",
                },
                {
                    "tag": "remote_proxy",
                    # DoH through the SOCKS proxy avoids port-53 blocking and
                    # UDP ASSOCIATE limitations in Xray's SOCKS inbound.
                    "type": "https",
                    "server": DNS_IP_GOOGLE,
                    "domain_resolver": "bootstrap",
                    "detour": "proxy",
                },
            ],
            "rules": [],
            "final": "remote_proxy",
            # IPv4-only: never query AAAA to avoid IPv6 stack errors and
            # latency spikes while IPv6 is disabled on the TUN adapter.
            "strategy": "ipv4_only",
            "disable_cache": False,
            "disable_expire": False,
            "independent_cache": True,
        }
