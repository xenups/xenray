"""DNS configuration for Xray."""

from loguru import logger

from src.core.app_context import AppContext
from src.core.constants import (
    CONFIG_ADDRESS,
    CONFIG_DNS,
    CONFIG_DOMAINS,
    CONFIG_PROTOCOL,
    CONFIG_QUERY_STRATEGY,
    CONFIG_SERVERS,
    DNS_DOH,
    DNS_DOQ,
    DNS_DOT,
    DNS_IP_CLOUDFLARE,
    DNS_IP_GOOGLE,
    DNS_UDP,
    DNS_USE_IP,
    TAG_DIRECT,
    TAG_PROXY,
)
from src.services.config_utils import is_ip


class DnsConfigurator:
    """Handles DNS server configuration for Xray configs."""

    def __init__(self, app_context: AppContext):
        self._app_context = app_context

    def configure(
        self,
        config: dict,
        mode: str = "proxy",
        proxy_server_ips: list = None,
        routing_rules: dict = None,
    ):
        """Configure DNS servers in config from user settings."""
        dns_config = self._app_context.dns.load()

        if mode == "vpn":
            # VPN/TUN mode: leak-free DNS via server-side resolution (no DoH).
            #
            # Routing uses "AsIs" domainStrategy (set by TunInjector), so raw
            # destination domains are passed to the egress server untouched and it
            # resolves them with its own system DNS. The DNS servers below remain
            # in place for the cases that still need client-side resolution:
            #
            # 1. Remote DNS (detour=TAG_PROXY): general system/app DNS queries
            #    (e.g. port 53) are answered with standard UDP DNS (1.1.1.1 /
            #    8.8.8.8) sent inside the existing encrypted tunnel.
            #
            # 2. Bootstrap/Direct (detour=TAG_DIRECT): restricted to the proxy
            #    server's own domain, explicit user direct bypass domains and
            #    Windows NCSI probe domains.
            bootstrap_domains = [
                "msftconnecttest.com",
                "msftncsi.com",
                "www.msftconnecttest.com",
                "www.msftncsi.com",
                "ipv6.msftconnecttest.com",
                "ipv6.msftncsi.com",
            ]

            # Add proxy server domains to bootstrap DNS so they can be resolved directly
            if proxy_server_ips:
                for ip_or_domain in proxy_server_ips:
                    if not is_ip(ip_or_domain):
                        bootstrap_domains.append(ip_or_domain)

            # Add user direct domains to bootstrap DNS
            if routing_rules:
                user_direct = routing_rules.get(TAG_DIRECT, [])
                for rule in user_direct:
                    if not rule.startswith("geoip:"):
                        bootstrap_domains.append(rule)

            bootstrap_domains = list(set(bootstrap_domains))

            # Primary: standard UDP Remote DNS servers detoured through the proxy.
            # Only IP addresses are usable here — DoH/DoT/DoQ entries are skipped.
            remote_servers = []
            for item in dns_config:
                addr = item.get(CONFIG_ADDRESS, "")
                if not addr:
                    continue
                bare = DnsConfigurator._to_bare_address(addr)
                if bare and is_ip(bare):
                    remote_servers.append({"address": bare, "detour": TAG_PROXY})

            if not remote_servers:
                remote_servers.append({"address": DNS_IP_CLOUDFLARE, "detour": TAG_PROXY})

            # Secondary: restricted Direct/Bootstrap DNS server. Pick an address
            # that does not collide with the remote server so routing stays clean.
            bootstrap_addr = DNS_IP_GOOGLE
            remote_addrs = {s["address"] for s in remote_servers}
            if bootstrap_addr in remote_addrs:
                bootstrap_addr = DNS_IP_CLOUDFLARE

            if CONFIG_DNS not in config:
                config[CONFIG_DNS] = {}

            # STRICT domain bounds on every direct resolver:
            # A TAG_DIRECT server MUST always carry a non-empty "domains"
            # restriction. In Xray a server without "domains" is a catch-all for
            # ALL queries, so an unbounded direct server would resolve general
            # domains via the local ISP DNS and leak. If the restricted set is
            # ever empty, the direct server is SKIPPED entirely rather than
            # emitted as a catch-all — general domains can only ever resolve
            # through the remote (TAG_PROXY) server below.
            servers_list = list(remote_servers)
            if bootstrap_domains:
                servers_list.append(
                    {
                        "address": bootstrap_addr,
                        "detour": TAG_DIRECT,
                        CONFIG_DOMAINS: bootstrap_domains,
                    }
                )

            config[CONFIG_DNS][CONFIG_SERVERS] = servers_list
            config[CONFIG_DNS][CONFIG_QUERY_STRATEGY] = DNS_USE_IP
            logger.info(f"[DnsConfigurator] Configured leak-free DNS (VPN mode) with {len(servers_list)} servers")
            return

        # Fallback to standard proxy mode DNS configuration
        servers = []
        for item in dns_config:
            addr = item.get(CONFIG_ADDRESS, "")
            if not addr:
                continue

            proto = item.get(CONFIG_PROTOCOL, DNS_UDP)

            if proto == DNS_DOH:
                if not addr.startswith("https://"):
                    addr = f"https://{addr}/dns-query"
            elif proto == DNS_DOT:
                if not addr.startswith("tls://"):
                    addr = f"tls://{addr}"
            elif proto == DNS_DOQ:
                if not addr.startswith("quic://"):
                    addr = f"quic://{addr}"

            domains = item.get(CONFIG_DOMAINS, [])
            entry = {CONFIG_ADDRESS: addr, "domains": domains} if domains else addr
            servers.append(entry)

        if CONFIG_DNS not in config:
            config[CONFIG_DNS] = {}

        FALLBACK_DNS = DNS_IP_CLOUDFLARE
        fallback_addrs = {s if isinstance(s, str) else s.get(CONFIG_ADDRESS, "") for s in servers}
        if FALLBACK_DNS not in fallback_addrs:
            servers.append(FALLBACK_DNS)

        config[CONFIG_DNS][CONFIG_SERVERS] = servers if servers else [DNS_IP_CLOUDFLARE, DNS_IP_GOOGLE]

        if CONFIG_QUERY_STRATEGY not in config[CONFIG_DNS]:
            config[CONFIG_DNS][CONFIG_QUERY_STRATEGY] = DNS_USE_IP

        logger.info(
            f"[DnsConfigurator] Configured {len(config[CONFIG_DNS][CONFIG_SERVERS])} DNS server(s) with fallback"
        )

    @staticmethod
    def _to_bare_address(address: str) -> str:
        """Strip DoH/DoT/DoQ scheme prefixes and URL paths down to a bare host/IP.

        Example: ``https+local://1.1.1.1/dns-query`` -> ``1.1.1.1``
        """
        bare = address
        for prefix in ("https+local://", "https://", "tls://", "quic://", "udp://"):
            if bare.startswith(prefix):
                bare = bare[len(prefix) :]
        if "/" in bare:
            bare = bare.split("/")[0]
        if ":" in bare and bare.count(":") == 1:
            bare = bare.split(":")[0]
        return bare

    def build_tun_servers(self) -> list:
        """Build DNS server list for TUN inbound from user configuration."""
        dns_config = self._app_context.dns.load()
        servers = []
        for item in dns_config:
            addr = item.get(CONFIG_ADDRESS, "")
            if not addr:
                continue
            # Windows/Wintun adapter DNS settings only accept bare IP addresses.
            if is_ip(addr):
                servers.append(addr)
        return servers if servers else [DNS_IP_CLOUDFLARE]
