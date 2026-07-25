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

