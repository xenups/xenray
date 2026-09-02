"""Sing-box DNS configuration builder."""

from __future__ import annotations

from typing import Optional

from src.core.constants import DNS_IP_CLOUDFLARE, DNS_IP_GOOGLE


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
        if local_dns_server and local_dns_server != "local":
            local_dns_entry = {
                "tag": "local_dns",
                "type": "udp",
                "server": local_dns_server,
            }
        else:
            local_dns_entry = {
                "tag": "local_dns",
                "type": "local",
            }

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
                local_dns_entry,
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
