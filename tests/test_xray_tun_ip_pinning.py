"""TUN-mode outbound IP pinning: Xray must never issue DNS in TUN mode
(its queries would TUN -> sing-box -> remote_proxy -> Xray recursion loop)."""

from __future__ import annotations


import pytest

from src.services.core_engines.xray_config_processor import XrayConfigProcessor


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch):
    """Never touch the network in tests: getaddrinfo -> fixed IPv4."""
    import socket

    def _fake_getaddrinfo(host, *a, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("185.105.239.126", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)


def _vless_config(address: str = "my.proxy.example.com") -> dict:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": address,
                            "port": 443,
                            "users": [{"id": "00000000-0000-0000-0000-000000000000"}],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "tls",
                    "tlsSettings": {"serverName": address, "allowInsecure": False},
                },
            },
            {"tag": "direct", "protocol": "freedom", "settings": {}},
        ],
    }


class TestPinOutboundServerIp:
    def test_skips_when_not_tun(self):
        config = _vless_config()
        XrayConfigProcessor(app_context=None).pin_outbound_server_ip(config, use_tun=False)
        outbound = config["outbounds"][0]
        assert outbound["settings"]["vnext"][0]["address"] == "my.proxy.example.com"

    def test_pins_domain_to_resolved_ip_in_tun_mode(self):
        config = _vless_config()
        XrayConfigProcessor(app_context=None).pin_outbound_server_ip(config, use_tun=True)
        address = config["outbounds"][0]["settings"]["vnext"][0]["address"]
        # Pinned to an IPv4 literal; serverName (SNI) stays the original domain.
        assert "." in address and address[0].isdigit(), address
        assert (
            config["outbounds"][0]["streamSettings"]["tlsSettings"]["serverName"]
            == "my.proxy.example.com"
        )

    def test_keeps_existing_ip_untouched(self):
        config = _vless_config(address="185.105.239.126")
        XrayConfigProcessor(app_context=None).pin_outbound_server_ip(config, use_tun=True)
        assert config["outbounds"][0]["settings"]["vnext"][0]["address"] == "185.105.239.126"

    def test_trojan_servers_entry_pinned(self):
        config = {
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "trojan",
                    "settings": {
                        "servers": [
                            {"address": "trojan.example.com", "port": 443, "password": "x"}
                        ]
                    },
                }
            ]
        }
        XrayConfigProcessor(app_context=None).pin_outbound_server_ip(config, use_tun=True)
        address = config["outbounds"][0]["settings"]["servers"][0]["address"]
        assert address[0].isdigit(), address
