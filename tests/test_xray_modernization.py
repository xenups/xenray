"""Tests for Xray-core v26.9.9 integration and modernization."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.core.constants import XRAY_VERSION
from src.core.parsers.vless import VlessParser
from src.platform.linux.core_assets import LinuxCoreAssetAdapter
from src.platform.macos.core_assets import MacosCoreAssetAdapter
from src.platform.windows.core_assets import WindowsCoreAssetAdapter
from src.services.core_engines.config_patcher import ConfigPatcher
from src.services.core_engines.xray_config_processor import XrayConfigProcessor


def test_xray_version_pinned_to_26_9_9():
    """Verify XRAY_VERSION constant is pinned to 26.9.9."""
    assert XRAY_VERSION == "26.9.9"


def test_platform_adapters_xray_26_9_9():
    """Verify platform asset adapters resolve correct URLs and assets for v26.9.9."""
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
