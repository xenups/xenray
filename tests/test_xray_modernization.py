"""Tests for Xray-core v26.10.10 integration and modernization."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.core.constants import PROTOCOL_MASQUE, PROTOCOL_WIREGUARD, TUN_GATEWAY_IPV4, TUN_ROUTE_IPV4, XRAY_VERSION
from src.core.parsers.binary_parser_adapter import LibXrayParserAdapter
from src.core.parsers.vless import VlessParser
from src.platform.linux.core_assets import LinuxCoreAssetAdapter
from src.platform.macos.core_assets import MacosCoreAssetAdapter
from src.platform.windows.core_assets import WindowsCoreAssetAdapter
from src.services.connection.tun_injector import TunInjector
from src.services.core_engines.config_patcher import ConfigPatcher
from src.services.core_engines.xray_config_processor import XrayConfigProcessor


def test_xray_version_pinned_to_26_10_17():
    """Verify XRAY_VERSION constant is pinned to 26.10.17."""
    assert XRAY_VERSION == "26.10.17"


def test_platform_adapters_xray_26_10_17():
    """Verify platform asset adapters resolve correct URLs and assets for v26.10.17."""
    win_adapter = WindowsCoreAssetAdapter()
    with patch("src.utils.platform_utils.PlatformUtils.get_architecture", return_value="x86_64"):
        win_info = win_adapter.get_xray_asset_info(XRAY_VERSION)
        assert win_info.filename == "Xray-windows-64.zip"
        assert f"v{XRAY_VERSION}" in win_info.download_url
        assert win_info.binary_name == "xray.exe"

    linux_adapter = LinuxCoreAssetAdapter()
    with patch("src.utils.platform_utils.PlatformUtils.get_architecture", return_value="x86_64"):
        linux_info = linux_adapter.get_xray_asset_info(XRAY_VERSION)
        assert linux_info.filename == "Xray-linux-64.zip"
        assert f"v{XRAY_VERSION}" in linux_info.download_url
        assert linux_info.binary_name == "xray"

    macos_adapter = MacosCoreAssetAdapter()
    with patch("src.utils.platform_utils.PlatformUtils.get_architecture", return_value="arm64"):
        macos_info = macos_adapter.get_xray_asset_info(XRAY_VERSION)
        assert macos_info.filename == "Xray-macos-arm64-v8a.zip"
        assert f"v{XRAY_VERSION}" in macos_info.download_url
        assert macos_info.binary_name == "xray"


def test_vless_vision_flow_disables_mux():
    """VLESS link with xtls-rprx-vision flow must explicitly disable MUX."""
    link = (
        "vless://00000000-0000-0000-0000-000000000001@example.com:443"
        "?security=reality&sni=test.com&pbk=12345678901234567890123456789012"
        "&flow=xtls-rprx-vision#Node1"
    )
    parsed = VlessParser.parse(link)
    outbound = parsed["config"]["outbounds"][0]

    assert outbound["protocol"] == "vless"
    assert outbound["settings"]["vnext"][0]["users"][0]["flow"] == "xtls-rprx-vision"
    assert "mux" in outbound
    assert outbound["mux"]["enabled"] is False


def test_vless_legacy_flow_sanitized():
    """VLESS link with deprecated flow (xtls-rprx-origin) is sanitized to xtls-rprx-vision."""
    link = (
        "vless://00000000-0000-0000-0000-000000000001@example.com:443"
        "?security=reality&sni=test.com&pbk=12345678901234567890123456789012"
        "&flow=xtls-rprx-origin#LegacyNode"
    )
    parsed = VlessParser.parse(link)
    outbound = parsed["config"]["outbounds"][0]

    assert outbound["settings"]["vnext"][0]["users"][0]["flow"] == "xtls-rprx-vision"
    assert outbound["mux"]["enabled"] is False


def test_config_patcher_mux_hardening_for_vision():
    """ConfigPatcher._apply_mux_hardening ensures MUX is disabled on existing configs with Vision."""
    patcher = ConfigPatcher()
    outbound = {
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": "example.com",
                    "port": 443,
                    "users": [{"id": "uuid-1", "flow": "xtls-rprx-vision"}],
                }
            ]
        },
        "streamSettings": {"network": "tcp", "security": "reality"},
        "mux": {"enabled": True},
    }

    applied = patcher._apply_mux_hardening(outbound)
    assert applied is True
    assert outbound["mux"]["enabled"] is False


def test_config_patcher_leaves_non_vision_alone():
    """ConfigPatcher._apply_mux_hardening leaves non-vision protocols alone."""
    patcher = ConfigPatcher()
    outbound = {
        "protocol": "vmess",
        "settings": {
            "vnext": [
                {
                    "address": "example.com",
                    "port": 443,
                    "users": [{"id": "uuid-1"}],
                }
            ]
        },
        "streamSettings": {"network": "ws"},
        "mux": {"enabled": True},
    }

    applied = patcher._apply_mux_hardening(outbound)
    assert applied is False
    assert outbound["mux"]["enabled"] is True


def test_xray_config_processor_inbounds_and_outbounds():
    """XrayConfigProcessor generates proper inbounds with sniffing and ensures direct/block outbounds."""
    mock_ctx = MagicMock()
    mock_ctx.settings.get_proxy_port.return_value = 10808
    mock_ctx.settings.get_http_port.return_value = 10809
    mock_ctx.settings.get_allow_lan.return_value = False
    mock_ctx.settings.get_sni_spoof_enabled.return_value = False
    mock_ctx.settings.get_cipher_suites.return_value = ""
    mock_ctx.dns.load.return_value = []
    mock_ctx.routing.load_rules.return_value = None

    processor = XrayConfigProcessor(mock_ctx)
    raw_config = {
        "inbounds": [],
        "outbounds": [
            {
                "protocol": "vless",
                "tag": "proxy",
                "settings": {"vnext": [{"address": "1.2.3.4", "port": 443}]},
            }
        ],
    }

    processed = processor.process_config(raw_config, mode="proxy")

    # Inbounds assertion
    inbounds = processed.get("inbounds", [])
    socks_ib = next((ib for ib in inbounds if ib.get("protocol") == "socks"), None)
    assert socks_ib is not None
    assert socks_ib["port"] == 10808
    assert socks_ib["listen"] == "127.0.0.1"
    assert socks_ib["sniffing"]["enabled"] is True
    assert "http" in socks_ib["sniffing"]["destOverride"]
    assert "tls" in socks_ib["sniffing"]["destOverride"]

    http_ib = next((ib for ib in inbounds if ib.get("protocol") == "http"), None)
    assert http_ib is not None
    assert http_ib["port"] == 10809
    assert http_ib["listen"] == "127.0.0.1"

    # Outbounds assertion
    outbound_tags = {ob.get("tag") for ob in processed.get("outbounds", [])}
    assert "direct" in outbound_tags
    assert "block" in outbound_tags


def test_config_patcher_warp_strips_redundant_public_key():
    """Verify ConfigPatcher strips redundant root-level publicKey in WARP/WireGuard outbounds."""
    patcher = ConfigPatcher()
    outbound = {
        "protocol": PROTOCOL_WIREGUARD,
        "tag": "warp-out",
        "settings": {
            "secretKey": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            "publicKey": "REDUNDANT_ROOT_PUBLIC_KEY_SHOULD_BE_REMOVED",
            "address": ["172.16.0.2/32"],
            "peers": [
                {
                    "publicKey": "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=",
                    "endpoint": "1.1.1.1:2408",
                }
            ],
        },
    }

    config = {"outbounds": [outbound]}
    patcher.safe_patch(config)

    assert "publicKey" not in outbound["settings"]
    assert outbound["settings"]["peers"][0]["publicKey"] == "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="


def test_config_patcher_masque_hardening():
    """Verify ConfigPatcher configures network 'masque' and security 'tls' for MASQUE outbounds."""
    patcher = ConfigPatcher()
    outbound = {
        "protocol": PROTOCOL_MASQUE,
        "tag": "masque-proxy",
        "settings": {
            "address": "example.com",
            "port": 443,
        },
        "streamSettings": {},
    }

    config = {"outbounds": [outbound]}
    patcher.safe_patch(config)

    stream = outbound["streamSettings"]
    assert stream["network"] == "masque"
    assert stream["security"] == "tls"
    assert "masqueSettings" in stream
    assert stream["tlsSettings"]["serverName"] == "example.com"


def test_tun_windows_wfp_leak_prevention():
    """Verify TunInjector injects autoSystemWfpBlockLeak on Windows."""
    mock_ctx = MagicMock()
    mock_ctx.routing.load_toggles.return_value = {}
    mock_ctx.routing.load_rules.return_value = {}
    mock_ctx.settings.get_sni_spoof_enabled.return_value = False

    injector = TunInjector(mock_ctx)
    config = {"inbounds": [], "routing": {"rules": []}}

    with patch("sys.platform", "win32"):
        injector.inject(config, dns_servers=["1.1.1.1"])

    tun = next(ib for ib in config["inbounds"] if ib.get("protocol") == "tun")
    assert "autoSystemWfpBlockLeak" in tun["settings"]
    assert tun["settings"]["autoSystemWfpBlockLeak"] == ["dns", "misconfigtun"]


def test_tun_handles_ipv6_disabled():
    """Verify TunInjector maintains IPv4-only routes and gateways when IPv6 is disabled."""
    mock_ctx = MagicMock()
    mock_ctx.routing.load_toggles.return_value = {}
    mock_ctx.routing.load_rules.return_value = {}
    mock_ctx.settings.get_sni_spoof_enabled.return_value = False

    injector = TunInjector(mock_ctx)
    config = {"inbounds": [], "routing": {"rules": []}}
    injector.inject(config, dns_servers=["1.1.1.1"])

    tun = next(ib for ib in config["inbounds"] if ib.get("protocol") == "tun")
    assert tun["settings"]["gateway"] == [TUN_GATEWAY_IPV4]
    assert tun["settings"]["autoSystemRoutingTable"] == [TUN_ROUTE_IPV4]
    # No IPv6 addresses present in gateway or routing table
    assert not any(":" in addr for addr in tun["settings"]["gateway"])
    assert not any(":" in route for route in tun["settings"]["autoSystemRoutingTable"])


def test_libxray_parser_masque_validation_fallback():
    """Verify LibXrayParserAdapter validates MASQUE configuration with bundled core."""
    from src.core.constants import XRAY_EXECUTABLE

    if not (XRAY_EXECUTABLE and os.path.isfile(XRAY_EXECUTABLE)):
        pytest.skip("Bundled Xray core binary not available for fallback validation")

    masque_cfg = {
        "outbounds": [
            {
                "protocol": "masque",
                "tag": "proxy",
                "settings": {"address": "1.1.1.1", "port": 443},
                "streamSettings": {"network": "masque", "security": "tls"},
            }
        ]
    }
    is_valid, err = LibXrayParserAdapter.validate_config(masque_cfg)
    assert is_valid is True, f"MASQUE validation failed: {err}"
    assert err is None


def test_libxray_parser_masque_validation_fallback_mocked():
    """Verify LibXrayParserAdapter falls back to xray executable when parser rejects MASQUE."""
    masque_cfg = {
        "outbounds": [
            {
                "protocol": "masque",
                "tag": "proxy",
                "settings": {"address": "1.1.1.1", "port": 443},
                "streamSettings": {"network": "masque", "security": "tls"},
            }
        ]
    }

    mock_parser_proc = MagicMock(
        returncode=0,
        stdout=b'{"success": false, "error": "unknown transport protocol: masque"}',
        stderr=b"",
    )
    mock_xray_proc = MagicMock(
        returncode=0,
        stdout=b"Configuration OK.",
        stderr=b"",
    )

    with patch("subprocess.run", side_effect=[mock_parser_proc, mock_xray_proc]):
        with patch("os.path.isfile", return_value=True):
            is_valid, err = LibXrayParserAdapter.validate_config(masque_cfg)
            assert is_valid is True, f"MASQUE validation failed: {err}"
            assert err is None
