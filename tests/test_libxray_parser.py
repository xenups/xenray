"""Unit tests for LibXrayParserAdapter and compiled Go xray-parser CLI tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.parsers.binary_parser_adapter import LibXrayParserAdapter
from src.core.parsers.vless import VlessParser


def test_adapter_availability():
    """Verify LibXrayParserAdapter discovers the compiled binary in bin/."""
    assert LibXrayParserAdapter.is_available() is True


def test_adapter_parse_vless_tls():
    """Verify VLESS TLS link parsing via libXray binary."""
    link = (
        "vless://00000000-0000-0000-0000-000000000001@example.com:443"
        "?security=tls&sni=example.com&type=ws&path=%2Fws#NodeTLS"
    )
    res = LibXrayParserAdapter.parse(link)

    assert res["name"] == "NodeTLS"
    config = res["config"]
    assert "outbounds" in config
    assert len(config["outbounds"]) >= 1

    proxy_out = config["outbounds"][0]
    assert proxy_out["protocol"] == "vless"
    assert proxy_out["tag"] == "NodeTLS"
    assert proxy_out["streamSettings"]["security"] == "tls"
    assert proxy_out["streamSettings"]["network"] == "ws"


def test_adapter_parse_vmess():
    """Verify VMess link parsing via libXray binary."""
    link = (
        "vmess://eyJ2IjoiMiIsInBzIjoiVk1lc3NUZXN0IiwiYWRkIjoidm1lc3MuZXhhbXBsZS5jb20iLCJwb3J0IjoiNDQzIi"
        "wiaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDIiLCJhaWQiOiIwIiwic2N5IjoiYXV0byIs"
        "Im5ldCI6IndzIiwidHlwZSI6Im5vbmUiLCJob3N0Ijoidm1lc3MuZXhhbXBsZS5jb20iLCJwYXRoIjoiL3ZtZXNzIiw"
        "idGxzIjoidGxzIiwic25pIjoidm1lc3MuZXhhbXBsZS5jb20ifQ=="
    )
    res = LibXrayParserAdapter.parse(link)

    assert res["name"] == "VMessTest"
    proxy_out = res["config"]["outbounds"][0]
    assert proxy_out["protocol"] == "vmess"
    assert proxy_out["settings"]["address"] == "vmess.example.com"
    assert proxy_out["streamSettings"]["security"] == "tls"


def test_adapter_parse_trojan():
    """Verify Trojan link parsing via libXray binary."""
    link = (
        "trojan://00000000-0000-0000-0000-000000000003@trojan.example.com:443"
        "?security=tls&sni=trojan.example.com#TrojanTest"
    )
    res = LibXrayParserAdapter.parse(link)

    assert res["name"] == "TrojanTest"
    proxy_out = res["config"]["outbounds"][0]
    assert proxy_out["protocol"] == "trojan"
    assert proxy_out["settings"]["password"] == "00000000-0000-0000-0000-000000000003"


def test_adapter_parse_shadowsocks():
    """Verify Shadowsocks link parsing via libXray binary."""
    link = "ss://Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTpwYXNzd29yZA@ss.example.com:8388#SSTest"
    res = LibXrayParserAdapter.parse(link)

    assert res["name"] == "SSTest"
    proxy_out = res["config"]["outbounds"][0]
    assert proxy_out["protocol"] == "shadowsocks"
    assert proxy_out["settings"]["method"] == "chacha20-ietf-poly1305"


def test_adapter_empty_link_raises_value_error():
    """Empty link must raise ValueError."""
    with pytest.raises(ValueError, match="non-empty"):
        LibXrayParserAdapter.parse("")


def test_adapter_malformed_link_raises_value_error():
    """Malformed link must raise ValueError with error message from parser."""
    with pytest.raises(ValueError, match="xray-parser failed"):
        LibXrayParserAdapter.parse("vless://invalid-malformed-no-address")


def test_adapter_fallback_when_unavailable():
    """When binary is unavailable, parse_with_fallback delegates to Python parser."""
    mock_fallback = MagicMock(return_value={"name": "FallbackNode", "config": {}})
    with patch.object(LibXrayParserAdapter, "is_available", return_value=False):
        res = LibXrayParserAdapter.parse_with_fallback("vless://test", fallback_func=mock_fallback)
        assert res["name"] == "FallbackNode"
        mock_fallback.assert_called_once_with("vless://test")


def test_adapter_fallback_on_parse_exception():
    """When binary crashes or fails, parse_with_fallback calls fallback without raising."""
    mock_fallback = MagicMock(return_value={"name": "RecoveredNode", "config": {}})
    with patch.object(LibXrayParserAdapter, "parse", side_effect=ValueError("Binary crashed")):
        res = LibXrayParserAdapter.parse_with_fallback("vless://test", fallback_func=mock_fallback)
        assert res["name"] == "RecoveredNode"
        mock_fallback.assert_called_once_with("vless://test")


def test_adapter_shadow_test_diff_execution():
    """Shadow-testing executes both parsers and logs differences without disrupting flow."""
    link = (
        "vless://00000000-0000-0000-0000-000000000001@example.com:443"
        "?security=tls&sni=example.com&type=ws&path=%2Fws#ShadowNode"
    )
    res = LibXrayParserAdapter.parse_with_fallback(
        link,
        fallback_func=VlessParser.parse,
        shadow_test=True,
    )
    assert res["name"] == "ShadowNode"
    assert res["config"]["outbounds"][0]["protocol"] == "vless"


def test_adapter_parse_batch_multiple_links():
    """Verify batch parsing of multiple links in a single invocation."""
    links = [
        (
            "vless://00000000-0000-0000-0000-000000000001@example.com:443"
            "?security=tls&sni=example.com&type=ws&path=%2Fws#Batch1"
        ),
        (
            "vless://00000000-0000-0000-0000-000000000002@example2.com:443"
            "?security=tls&sni=example2.com&type=ws&path=%2Fws#Batch2"
        ),
    ]
    items = LibXrayParserAdapter.parse_batch(links)
    assert len(items) == 2
    assert items[0]["name"] == "Batch1"
    assert items[1]["name"] == "Batch2"
    assert items[0]["config"]["outbounds"][0]["protocol"] == "vless"
    assert items[1]["config"]["outbounds"][0]["protocol"] == "vless"


def test_adapter_get_xray_version():
    """Verify get_xray_version returns non-empty core version string."""
    if not LibXrayParserAdapter.is_available():
        pytest.skip("xray-parser binary not built yet")
    version = LibXrayParserAdapter.get_xray_version()
    assert version is not None
    assert "26." in version


def test_adapter_validate_config():
    """Verify validate_config accepts valid config and catches invalid config."""
    if not LibXrayParserAdapter.is_available():
        pytest.skip("xray-parser binary not built yet")

    valid_cfg = {
        "log": {"loglevel": "warning"},
        "inbounds": [],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}],
    }
    is_valid, err = LibXrayParserAdapter.validate_config(valid_cfg)
    assert is_valid is True
    assert err is None

    invalid_cfg = {
        "inbounds": [{"protocol": "unsupported_protocol"}],
    }
    is_valid_bad, err_bad = LibXrayParserAdapter.validate_config(invalid_cfg)
    assert is_valid_bad is False
    assert err_bad is not None
