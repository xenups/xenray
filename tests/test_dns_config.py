"""Tests for DNS configuration in XrayConfigProcessor."""

from unittest.mock import Mock

import pytest

from src.core.constants import DNS_IP_CLOUDFLARE
from src.services.connection.dns_configurator import DnsConfigurator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_dns():
    """Fixture for a mocked DNS repository."""
    dns = Mock()
    dns.load.return_value = []
    return dns


@pytest.fixture
def dns_configurator(mock_dns):
    """Fixture providing a DnsConfigurator with mocked DNS repository."""
    ctx = Mock()
    ctx.dns = mock_dns
    return DnsConfigurator(ctx)


# ---------------------------------------------------------------------------
# configure — protocol tests
# ---------------------------------------------------------------------------


class TestConfigureDns:
    """Tests for DnsConfigurator.configure()."""

    def test_udp(self, dns_configurator, mock_dns):
        """UDP DNS server is passed through as bare address."""
        mock_dns.load.return_value = [
            {"address": "9.9.9.9", "protocol": "udp", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert "9.9.9.9" in servers
        assert "1.1.1.1" in servers  # fallback

    def test_tcp(self, dns_configurator, mock_dns):
        """TCP DNS server is passed through as bare address."""
        mock_dns.load.return_value = [
            {"address": "9.9.9.9", "protocol": "tcp", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert "9.9.9.9" in servers

    def test_doh(self, dns_configurator, mock_dns):
        """DoH server gets https:// prefix and /dns-query path."""
        mock_dns.load.return_value = [
            {"address": "dns.cloudflare.com", "protocol": "doh", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert "https://dns.cloudflare.com/dns-query" in servers

    def test_doh_preserves_existing_prefix(self, dns_configurator, mock_dns):
        """DoH server already starting with https:// is not double-prefixed."""
        mock_dns.load.return_value = [
            {
                "address": "https://custom.dns/endpoint",
                "protocol": "doh",
                "domains": [],
            },
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert "https://custom.dns/endpoint" in servers

    def test_dot(self, dns_configurator, mock_dns):
        """DoT server gets tls:// prefix."""
        mock_dns.load.return_value = [
            {"address": "dns.google", "protocol": "dot", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert "tls://dns.google" in servers

    def test_dot_preserves_existing_prefix(self, dns_configurator, mock_dns):
        """DoT server already starting with tls:// is not double-prefixed."""
        mock_dns.load.return_value = [
            {"address": "tls://dns.google", "protocol": "dot", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert "tls://dns.google" in servers

    def test_doq(self, dns_configurator, mock_dns):
        """DoQ server gets quic:// prefix."""
        mock_dns.load.return_value = [
            {"address": "dns.nextdns.io", "protocol": "doq", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert "quic://dns.nextdns.io" in servers

    def test_doq_preserves_existing_prefix(self, dns_configurator, mock_dns):
        """DoQ server already starting with quic:// is not double-prefixed."""
        mock_dns.load.return_value = [
            {"address": "quic://dns.nextdns.io", "protocol": "doq", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert "quic://dns.nextdns.io" in servers

    def test_empty_address_skipped(self, dns_configurator, mock_dns):
        """Entries with empty address are skipped."""
        mock_dns.load.return_value = [
            {"address": "", "protocol": "udp", "domains": []},
            {"address": "1.1.1.1", "protocol": "udp", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert len(servers) >= 1
        assert "1.1.1.1" in servers

    def test_domains_dict_entry(self, dns_configurator, mock_dns):
        """Entries with domains produce a dict instead of plain string."""
        mock_dns.load.return_value = [
            {"address": "9.9.9.9", "protocol": "udp", "domains": ["example.com"]},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        entry = next(s for s in servers if isinstance(s, dict) and s.get("address") == "9.9.9.9")
        assert entry["domains"] == ["example.com"]

    def test_mixed_entries(self, dns_configurator, mock_dns):
        """Multiple DNS entries of different protocols are all included."""
        mock_dns.load.return_value = [
            {"address": "9.9.9.9", "protocol": "udp", "domains": []},
            {"address": "dns.google", "protocol": "dot", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert "9.9.9.9" in servers
        assert "tls://dns.google" in servers

    def test_query_strategy_default(self, dns_configurator, mock_dns):
        """Proxy mode uses UseIPv4 as the safe default (no AAAA timeouts)."""
        config = {}
        dns_configurator.configure(config)
        assert config["dns"]["queryStrategy"] == "UseIPv4"

    def test_query_strategy_preserved(self, dns_configurator, mock_dns):
        """Existing queryStrategy is not overridden."""
        config = {"dns": {"queryStrategy": "UseIPv4"}}
        dns_configurator.configure(config)
        assert config["dns"]["queryStrategy"] == "UseIPv4"


# ---------------------------------------------------------------------------
# configure — fallback tests
# ---------------------------------------------------------------------------


class TestConfigureDnsFallback:
    """Tests for DNS fallback behavior."""

    def test_empty_list_uses_fallback(self, dns_configurator, mock_dns):
        """When user DNS list is empty, fall back to 1.1.1.1."""
        mock_dns.load.return_value = []
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert servers == ["1.1.1.1"]

    def test_fallback_appended_to_user_servers(self, dns_configurator, mock_dns):
        """Fallback 1.1.1.1 is appended when user configures custom DNS."""
        mock_dns.load.return_value = [
            {"address": "9.9.9.9", "protocol": "udp", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert "9.9.9.9" in servers
        assert "1.1.1.1" in servers

    def test_fallback_not_duplicated(self, dns_configurator, mock_dns):
        """When user already has 1.1.1.1, fallback is not duplicated."""
        mock_dns.load.return_value = [
            {"address": "1.1.1.1", "protocol": "udp", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        assert servers.count("1.1.1.1") == 1

    def test_fallback_not_duplicated_in_dict(self, dns_configurator, mock_dns):
        """When user has 1.1.1.1 as a dict entry, fallback is not duplicated."""
        mock_dns.load.return_value = [
            {"address": "1.1.1.1", "protocol": "udp", "domains": ["example.com"]},
        ]
        config = {}
        dns_configurator.configure(config)
        servers = config["dns"]["servers"]
        dict_entries = [s for s in servers if isinstance(s, dict)]
        str_entries = [s for s in servers if isinstance(s, str)]
        assert len(dict_entries) == 1
        assert dict_entries[0]["address"] == "1.1.1.1"
        # No additional plain-string fallback since user already has 1.1.1.1
        assert "1.1.1.1" not in str_entries


# ---------------------------------------------------------------------------
# build_tun_servers tests
# ---------------------------------------------------------------------------


class TestConfigureVpnDns:
    """Tests for DnsConfigurator.configure() in VPN mode (leak-free Remote DNS)."""

    def test_vpn_remote_server_via_proxy(self, dns_configurator, mock_dns):
        """General remote DNS is a standard UDP IP detoured through the proxy."""
        mock_dns.load.return_value = [
            {"address": "1.1.1.1", "protocol": "udp", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config, mode="vpn")
        servers = config["dns"]["servers"]
        remote = next(s for s in servers if s.get("detour") == "proxy")
        assert remote["address"] == "1.1.1.1"
        assert "https+local://" not in remote["address"]
        assert "dns-query" not in remote["address"]

    def test_vpn_default_remote_no_doh(self, dns_configurator, mock_dns):
        """Empty DNS config falls back to plain UDP 1.1.1.1 via proxy (no DoH)."""
        mock_dns.load.return_value = []
        config = {}
        dns_configurator.configure(config, mode="vpn")
        servers = config["dns"]["servers"]
        remote = next(s for s in servers if s.get("detour") == "proxy")
        assert remote["address"] == "1.1.1.1"
        assert "https+local://" not in remote["address"]

    def test_vpn_bootstrap_server_restricted_domains(self, dns_configurator, mock_dns):
        """Direct/bootstrap DNS is restricted to NCSI + proxy server + user direct domains."""
        mock_dns.load.return_value = [
            {"address": "1.1.1.1", "protocol": "udp", "domains": []},
        ]
        config = {}
        dns_configurator.configure(
            config,
            mode="vpn",
            proxy_server_ips=["proxy.example.com"],
            routing_rules={"direct": ["direct.com"], "proxy": [], "block": []},
        )
        servers = config["dns"]["servers"]
        bootstrap = next(s for s in servers if s.get("detour") == "direct")
        assert "proxy.example.com" in bootstrap["domains"]
        assert "direct.com" in bootstrap["domains"]
        assert "msftconnecttest.com" in bootstrap["domains"]

    def test_vpn_bootstrap_address_differs_from_remote(self, dns_configurator, mock_dns):
        """Bootstrap direct server uses a different IP than the remote proxy server."""
        mock_dns.load.return_value = [
            {"address": "1.1.1.1", "protocol": "udp", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config, mode="vpn")
        servers = config["dns"]["servers"]
        remote = next(s for s in servers if s.get("detour") == "proxy")
        bootstrap = next(s for s in servers if s.get("detour") == "direct")
        assert remote["address"] != bootstrap["address"]

    def test_vpn_query_strategy_ipv4_only(self, dns_configurator, mock_dns):
        """VPN mode forces UseIPv4 query strategy (IPv6 disabled on the TUN)."""
        mock_dns.load.return_value = []
        config = {}
        dns_configurator.configure(config, mode="vpn")
        assert config["dns"]["queryStrategy"] == "UseIPv4"

    def test_vpn_direct_server_always_has_domains(self, dns_configurator, mock_dns):
        """Direct/bootstrap servers must always carry strict domain bounds (never a catch-all)."""
        mock_dns.load.return_value = []
        config = {}
        dns_configurator.configure(config, mode="vpn")
        servers = config["dns"]["servers"]
        for s in servers:
            if s.get("detour") == "direct":
                assert s.get("domains"), f"Direct server {s['address']} must have a domains restriction"
                assert len(s["domains"]) > 0

    def test_vpn_general_resolution_only_via_proxy(self, dns_configurator, mock_dns):
        """Catch-all resolvers (no domains) must be proxy-only — never direct."""
        mock_dns.load.return_value = [
            {"address": "9.9.9.9", "protocol": "udp", "domains": []},
        ]
        config = {}
        dns_configurator.configure(config, mode="vpn")
        servers = config["dns"]["servers"]
        catch_alls = [s for s in servers if not s.get("domains")]
        assert catch_alls, "Expected at least one catch-all remote resolver"
        assert all(s.get("detour") == "proxy" for s in catch_alls)

    def test_vpn_no_localhost_server(self, dns_configurator, mock_dns):
        """Server-side resolution relies on AsIs domainStrategy, not a 'localhost' DNS server."""
        mock_dns.load.return_value = []
        config = {}
        dns_configurator.configure(config, mode="vpn")
        servers = config["dns"]["servers"]
        assert all(s.get("address") != "localhost" for s in servers if isinstance(s, dict))

    def test_vpn_strips_doh_prefix(self, dns_configurator, mock_dns):
        """DoH entries are reduced to bare IP for remote UDP DNS (no DoH)."""
        mock_dns.load.return_value = [
            {
                "address": "https+local://1.1.1.1/dns-query",
                "protocol": "doh",
                "domains": [],
            },
        ]
        config = {}
        dns_configurator.configure(config, mode="vpn")
        servers = config["dns"]["servers"]
        remote = next(s for s in servers if s.get("detour") == "proxy")
        assert remote["address"] == "1.1.1.1"


class TestBuildTunDnsServers:
    """Tests for DnsConfigurator.build_tun_servers() (IPv4-only)."""

    def test_udp(self, dns_configurator, mock_dns):
        """UDP address is returned as bare address."""
        mock_dns.load.return_value = [
            {"address": "9.9.9.9", "protocol": "udp", "domains": []},
        ]
        servers = dns_configurator.build_tun_servers()
        assert "9.9.9.9" in servers

    def test_doh_domain_filtered(self, dns_configurator, mock_dns):
        """DoH domain name address is filtered out (not an IP)."""
        mock_dns.load.return_value = [
            {"address": "dns.cloudflare.com", "protocol": "doh", "domains": []},
        ]
        servers = dns_configurator.build_tun_servers()
        assert "dns.cloudflare.com" not in servers
        assert servers == [DNS_IP_CLOUDFLARE]

    def test_dot_domain_filtered(self, dns_configurator, mock_dns):
        """DoT domain name address is filtered out."""
        mock_dns.load.return_value = [
            {"address": "dns.google", "protocol": "dot", "domains": []},
        ]
        servers = dns_configurator.build_tun_servers()
        assert "dns.google" not in servers
        assert servers == [DNS_IP_CLOUDFLARE]

    def test_doq_domain_filtered(self, dns_configurator, mock_dns):
        """DoQ domain name address is filtered out."""
        mock_dns.load.return_value = [
            {"address": "dns.nextdns.io", "protocol": "doq", "domains": []},
        ]
        servers = dns_configurator.build_tun_servers()
        assert "dns.nextdns.io" not in servers
        assert servers == [DNS_IP_CLOUDFLARE]

    def test_empty_address_skipped(self, dns_configurator, mock_dns):
        """Empty address entries are filtered out."""
        mock_dns.load.return_value = [
            {"address": "", "protocol": "udp", "domains": []},
            {"address": "9.9.9.9", "protocol": "udp", "domains": []},
        ]
        servers = dns_configurator.build_tun_servers()
        assert "9.9.9.9" in servers
        assert "" not in servers

    def test_empty_list_uses_defaults(self, dns_configurator, mock_dns):
        """Empty DNS list falls back to the default IPv4 server."""
        mock_dns.load.return_value = []
        servers = dns_configurator.build_tun_servers()
        assert servers == [DNS_IP_CLOUDFLARE]

    def test_multiple_servers(self, dns_configurator, mock_dns):
        """Multiple DNS entries are included if they are valid IPv4 addresses."""
        mock_dns.load.return_value = [
            {"address": "9.9.9.9", "protocol": "udp", "domains": []},
            {"address": "dns.google", "protocol": "dot", "domains": []},
        ]
        servers = dns_configurator.build_tun_servers()
        assert "9.9.9.9" in servers
        assert "dns.google" not in servers
        assert len(servers) == 1

    def test_ipv6_resolver_dropped(self, dns_configurator, mock_dns):
        """IPv6 resolvers are excluded from the TUN adapter DNS (IPv4-only)."""
        mock_dns.load.return_value = [
            {"address": "9.9.9.9", "protocol": "udp", "domains": []},
            {"address": "2606:4700:4700::1111", "protocol": "udp", "domains": []},
        ]
        servers = dns_configurator.build_tun_servers()
        assert "9.9.9.9" in servers
        assert "2606:4700:4700::1111" not in servers
        assert all(":" not in s for s in servers), "No IPv6 resolvers allowed"
