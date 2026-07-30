"""Unit tests for CDN-backed configuration TUN bypass routing."""
from unittest.mock import Mock

import pytest

from src.services.singbox_tun_service import SingboxTunService
from src.services.tun_injector import TunInjector
from src.services.xray_config_processor import XrayConfigProcessor


@pytest.fixture
def mock_app_context():
    ctx = Mock()
    ctx.settings.get_proxy_port.return_value = 10808
    ctx.settings.get_tun_engine.return_value = "xray"
    ctx.settings.get_routing_country.return_value = ""
    ctx.routing.load_toggles.return_value = {"block_udp_443": False, "block_ads": False, "direct_private_ips": True}
    ctx.routing.load_rules.return_value = {"direct": [], "proxy": [], "block": []}
    ctx.dns.load.return_value = []
    return ctx


def test_get_proxy_server_ip_extracts_cdn_sni_and_host(mock_app_context):
    processor = XrayConfigProcessor(mock_app_context)
    config = {
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": "104.16.200.1",
                            "port": 443,
                        }
                    ]
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "tls",
                    "tlsSettings": {
                        "serverName": "cdn-sni.cloudflare-worker.dev",
                    },
                    "wsSettings": {
                        "headers": {
                            "Host": "cdn-host.cloudflare-worker.dev",
                        }
                    },
                },
            }
        ]
    }

    endpoints = processor.get_proxy_server_ip(config)
    assert "104.16.200.1" in endpoints
    assert "cdn-sni.cloudflare-worker.dev" in endpoints
    assert "cdn-host.cloudflare-worker.dev" in endpoints


def test_tun_injector_adds_direct_rules_for_cdn_endpoints(mock_app_context):
    injector = TunInjector(mock_app_context)
    config = {"inbounds": [], "routing": {"rules": []}}
    cdn_endpoints = ["104.16.200.1", "cdn-sni.cloudflare-worker.dev"]

    injector.inject(config, dns_servers=["1.1.1.1"], proxy_server_ips=cdn_endpoints)

    rules = config["routing"]["rules"]
    direct_ip_rules = [r for r in rules if r.get("outboundTag") == "direct" and "ip" in r]
    direct_domain_rules = [r for r in rules if r.get("outboundTag") == "direct" and "domain" in r]

    assert any("104.16.200.1" in r["ip"] for r in direct_ip_rules)
    assert any("cdn-sni.cloudflare-worker.dev" in r["domain"] for r in direct_domain_rules)
    assert any("1.1.1.1" in r["ip"] for r in direct_ip_rules)


def test_singbox_tun_service_generates_cdn_domain_bypass():
    service = SingboxTunService()
    cdn_endpoints = ["104.16.200.1", "cdn-sni.cloudflare-worker.dev"]

    config = service._generate_config(
        socks_port=10808,
        proxy_server_ip=cdn_endpoints,
    )

    rules = config["route"]["rules"]
    domain_bypass = [r for r in rules if r.get("outbound") == "direct" and "domain_suffix" in r]

    assert any(r["domain_suffix"] == "cdn-sni.cloudflare-worker.dev" for r in domain_bypass)


def test_get_proxy_server_ip_extracts_ech_outer_sni_and_config(mock_app_context):
    processor = XrayConfigProcessor(mock_app_context)
    config = {
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": "104.16.200.1",
                            "port": 443,
                        }
                    ]
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "tls",
                    "tlsSettings": {
                        "serverName": "inner-sni.encrypted.com",
                        "outerServerName": "outer-ech.cloudflare.net",
                        "ech": "outer-ech.cloudflare.net",
                    },
                },
            }
        ]
    }

    endpoints = processor.get_proxy_server_ip(config)
    assert "104.16.200.1" in endpoints
    assert "inner-sni.encrypted.com" in endpoints
    assert "outer-ech.cloudflare.net" in endpoints


def test_singbox_tun_service_bypasses_windows_ncsi():
    """Verify NCSI domains are injected as high-priority direct rules and use bootstrap DNS."""
    service = SingboxTunService()
    config = service._generate_config(
        socks_port=10808,
        proxy_server_ip=["104.16.200.1"],
        interface_name="Wi-Fi",
    )

    rules = config["route"]["rules"]
    dns_rules = config["dns"]["rules"]

    # Route rule: NCSI/localhost domains must be routed to direct outbound
    ncsi_route = next((r for r in rules if r.get("outbound") == "direct" and "domain_suffix" in r), None)
    assert ncsi_route is not None
    ncsi_domains = ncsi_route["domain_suffix"]
    assert "msftconnecttest.com" in ncsi_domains
    assert "msftncsi.com" in ncsi_domains
    assert "localhost" in ncsi_domains

    # DNS rule: NCSI/localhost domains must use bootstrap DNS (not remote_proxy)
    ncsi_dns = next((r for r in dns_rules if "domain_suffix" in r and r.get("server") == "bootstrap"), None)
    assert ncsi_dns is not None
    assert "msftconnecttest.com" in ncsi_dns["domain_suffix"]
    assert "msftncsi.com" in ncsi_dns["domain_suffix"]
    assert "localhost" in ncsi_dns["domain_suffix"]

    # NCSI rule must appear before the DNS hijack rule (higher priority)
    ncsi_idx = next(i for i, r in enumerate(rules) if r.get("outbound") == "direct" and "domain_suffix" in r)
    hijack_idx = next(i for i, r in enumerate(rules) if r.get("action") == "hijack-dns")
    assert ncsi_idx < hijack_idx, "NCSI bypass must be above DNS hijack"


def test_singbox_tun_service_enables_dynamic_interface_auto_detection():
    service = SingboxTunService()
    config = service._generate_config(
        socks_port=10808,
        proxy_server_ip=["104.16.200.1"],
        interface_name="Wi-Fi",
    )

    assert config["route"].get("auto_detect_interface") is True
    assert config["route"].get("default_interface") == "Wi-Fi"
    assert config["inbounds"][0].get("strict_route") is True

    direct_outbound = next(o for o in config["outbounds"] if o.get("tag") == "direct")
    assert direct_outbound.get("bind_interface") == "Wi-Fi"

    # Verify the active proxy endpoint /32 IP is injected as a high-priority direct rule
    rules = config["route"]["rules"]
    # Dynamic /32 rules use a string value; static pre-built rules (private ranges etc.) use a list
    dynamic_direct_rules = [r for r in rules if r.get("outbound") == "direct" and isinstance(r.get("ip_cidr"), str)]
    assert any("104.16.200.1/32" == r["ip_cidr"] for r in dynamic_direct_rules)

    # Verify no broad CDN CIDR ranges — dynamic rules are always /32 host routes
    assert all("/32" in r["ip_cidr"] for r in dynamic_direct_rules)


def test_singbox_tun_service_adds_static_route_for_proxy_ip(monkeypatch):
    """Verify that OS route add IS called for the proxy server IP (prevents loop)."""
    import subprocess as _subprocess

    service = SingboxTunService()

    assert hasattr(service, "_add_static_route")
    assert hasattr(service, "_cleanup_routes")
    assert hasattr(service, "_added_routes")

    call_log = []

    def tracking_run(*args, **kwargs):
        call_log.append(args[0] if args else kwargs.get("args", []))
        class MockResult:
            returncode = 0
            stdout = ""
            stderr = ""
        return MockResult()

    monkeypatch.setattr(_subprocess, "run", tracking_run)

    # Mock so start() doesn't actually run sing-box
    monkeypatch.setattr("src.services.singbox_tun_service.NetworkInterfaceDetector.get_primary_interface",
                        lambda: ("Wi-Fi", "192.168.1.10", "192.168.1.0/24", "192.168.1.1"))
    monkeypatch.setattr(service, "_resolve_ips", lambda endpoints: [e for e in endpoints if e == "104.16.200.1"])
    monkeypatch.setattr(service, "_wait_for_xray_ready", lambda port: False)
    monkeypatch.setattr(service, "_write_config_and_start", lambda config: False)

    service.start(xray_socks_port=10808, proxy_server_ip="104.16.200.1")

    # Must have called "route add" for 104.16.200.1
    route_calls = [args for args in call_log if any("route" in str(a).lower() for a in (args if isinstance(args, list) else [args]))]
    assert len(route_calls) >= 1, f"Expected route add for proxy IP, got: {route_calls}"
    assert any("104.16.200.1" in str(a) for args in route_calls for a in args), f"route add not called for proxy IP: {route_calls}"


def test_singbox_tun_service_injects_resolved_domain_ips():
    """Verify pre-resolved domain IPs are injected as /32 host routes alongside original proxy IPs."""
    service = SingboxTunService()
    config = service._generate_config(
        socks_port=10808,
        proxy_server_ip=["cdn-sni.cloudflare-worker.dev"],
        resolved_ips=["104.16.200.1", "104.16.200.2"],
    )

    rules = config["route"]["rules"]
    dynamic_direct_rules = [r for r in rules if r.get("outbound") == "direct" and isinstance(r.get("ip_cidr"), str)]

    # Resolved IPs must appear as /32 rules
    cidrs = {r["ip_cidr"] for r in dynamic_direct_rules}
    assert "104.16.200.1/32" in cidrs
    assert "104.16.200.2/32" in cidrs
    # Bootstrap DNS addresses must still be present
    assert "1.1.1.1/32" in cidrs
    assert "8.8.8.8/32" in cidrs


def test_singbox_tun_service_generated_config_has_no_broad_cdn_ranges():
    """Verify that only /32 host routes are used for proxy endpoints, never broad CDN CIDR ranges."""
    service = SingboxTunService()
    cdn_endpoints = ["104.16.200.1", "cdn-sni.cloudflare-worker.dev"]

    config = service._generate_config(
        socks_port=10808,
        proxy_server_ip=cdn_endpoints,
    )

    rules = config["route"]["rules"]
    # Only the proxy endpoint IP rules are inserted as /32 — all others (private, etc.) are pre-existing
    proxy_ip_rules = [
        r for r in rules
        if r.get("outbound") == "direct"
        and "ip_cidr" in r
        and not isinstance(r["ip_cidr"], list)  # /32 rules are single strings, private ranges are lists
    ]

    for rule in proxy_ip_rules:
        cidr = rule["ip_cidr"]
        assert "/32" in cidr, f"Found non-/32 proxy route: {cidr}"


def test_tun_injector_binds_direct_outbound_to_interface(mock_app_context):
    """Verify Xray freedom outbound gets sockopt.interface binding."""
    injector = TunInjector(mock_app_context)
    config = {"outbounds": [
        {"tag": "proxy", "protocol": "vless", "settings": {}},
        {"tag": "direct", "protocol": "freedom", "settings": {}},
    ]}
    cdn_endpoints = ["104.16.200.1", "cdn-sni.cloudflare-worker.dev"]

    injector.inject(config, dns_servers=["1.1.1.1"], proxy_server_ips=cdn_endpoints, interface_name="Wi-Fi")

    direct_out = next(o for o in config["outbounds"] if o.get("tag") == "direct")
    assert direct_out["streamSettings"]["sockopt"]["interface"] == "Wi-Fi"


def test_tun_injector_skips_sockopt_when_no_interface(mock_app_context):
    """Verify that without interface_name, the outbound is not modified."""
    injector = TunInjector(mock_app_context)
    config = {"outbounds": [
        {"tag": "proxy", "protocol": "vless", "settings": {}},
        {"tag": "direct", "protocol": "freedom", "settings": {}},
    ]}
    cdn_endpoints = ["104.16.200.1"]

    injector.inject(config, dns_servers=["1.1.1.1"], proxy_server_ips=cdn_endpoints)

    direct_out = next(o for o in config["outbounds"] if o.get("tag") == "direct")
    assert "streamSettings" not in direct_out


def test_network_interface_detector_selects_lowest_metric(monkeypatch):
    from src.utils.network_interface import NetworkInterfaceDetector

    mock_route_output = (
        "===========================================================================\n"
        "Active Routes:\n"
        "Network Destination        Netmask          Gateway       Interface  Metric\n"
        "          0.0.0.0          0.0.0.0      192.168.1.1     192.168.1.10     25\n"
        "          0.0.0.0          0.0.0.0   192.168.42.129    192.168.42.50     15\n"
        "===========================================================================\n"
    )

    class DummySubprocess:
        returncode = 0
        stdout = mock_route_output

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: DummySubprocess())
    monkeypatch.setattr(NetworkInterfaceDetector, "_get_interface_name", lambda ip: "USB Tethering" if "42" in ip else "Wi-Fi")

    iface_name, iface_ip, subnet, gateway = NetworkInterfaceDetector.get_primary_interface()

    assert iface_name == "USB Tethering"
    assert iface_ip == "192.168.42.50"
    assert gateway == "192.168.42.129"


