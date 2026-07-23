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
    DNS_UDP,
    DNS_USE_IP,
)
from src.services.config_utils import is_ip


class DnsConfigurator:
    """Handles DNS server configuration for Xray configs."""

    def __init__(self, app_context: AppContext):
        self._app_context = app_context

    def configure(self, config: dict):
        """Configure DNS servers in config from user settings."""
        dns_config = self._app_context.dns.load()

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

        FALLBACK_DNS = "1.1.1.1"
        fallback_addrs = {s if isinstance(s, str) else s.get(CONFIG_ADDRESS, "") for s in servers}
        if FALLBACK_DNS not in fallback_addrs:
            servers.append(FALLBACK_DNS)

        config[CONFIG_DNS][CONFIG_SERVERS] = servers if servers else ["1.1.1.1", "8.8.8.8"]

        if CONFIG_QUERY_STRATEGY not in config[CONFIG_DNS]:
            config[CONFIG_DNS][CONFIG_QUERY_STRATEGY] = DNS_USE_IP

        logger.info(
            f"[DnsConfigurator] Configured {len(config[CONFIG_DNS][CONFIG_SERVERS])} DNS server(s) with fallback"
        )

    def build_tun_servers(self) -> list:
        """Build DNS server list for TUN inbound from user configuration.

        TUN DNS servers must be bare IP addresses only — xray-core's TUN driver
        parses each entry with netip.ParseAddr(), which rejects domain names
        and protocol-prefixed URLs (https://, tls://, quic://).

        Non-IP entries are skipped. Falls back to ["1.1.1.1", "8.8.8.8"]
        when no valid IP entries exist.
        """
        dns_config = self._app_context.dns.load()
        servers = []
        for item in dns_config:
            addr = item.get(CONFIG_ADDRESS, "")
            if not addr or not is_ip(addr):
                continue
            servers.append(addr)
        return servers if servers else ["1.1.1.1", "8.8.8.8"]
