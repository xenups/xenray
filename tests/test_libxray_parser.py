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


def test_adapter_parse_fp_unsafe_and_cipher_suites():
    """Verify libXray adapter preserves fp=unsafe, cipherSuites, finalmask, and xhttp extra."""
    if not LibXrayParserAdapter.is_available():
        pytest.skip("xray-parser binary not built yet")

    mock_link = (
        "vless://00000000-0000-0000-0000-000000000001@example.com:443"
        "?security=tls&alpn=h2&fp=unsafe"
        "&cs=TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256"
        "&type=xhttp&mode=auto&path=/test"
        "&extra=%7B%22noSSEHeader%22%3Atrue%2C%22downloadProxy%22%3Atrue%7D"
        "&fm=%7B%22tcp%22%3A%5B%7B%22type%22%3A%22fragment%22%2C"
        "%22settings%22%3A%7B%22packets%22%3A%22tlshello%22%2C%22lengths%22%3A%5B%22100-200%22%5D%2C"
        "%22delays%22%3A%5B%2210-20%22%5D%7D%7D%5D%7D"
        "#UnsafeNode"
    )
    res = LibXrayParserAdapter.parse(mock_link)
    ob = res["config"]["outbounds"][0]
    tls = ob["streamSettings"]["tlsSettings"]
    xhttp = ob["streamSettings"]["xhttpSettings"]
    finalmask = ob["streamSettings"]["finalmask"]

    assert tls["fingerprint"] == "unsafe"
    assert tls["cipherSuites"] == "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256"
    assert xhttp["mode"] == "auto"
    assert xhttp["extra"]["noSSEHeader"] is True
    assert xhttp["extra"]["downloadProxy"] is True
    assert finalmask["tcp"][0]["type"] == "fragment"
    assert finalmask["tcp"][0]["settings"]["packets"] == "tlshello"


def test_adapter_parse_batch_distinct_parameters():
    """Verify batch parsing isolates per-node advanced parameters without cross-contamination."""
    if not LibXrayParserAdapter.is_available():
        pytest.skip("xray-parser binary not built yet")

    link_one = (
        "vless://00000000-0000-0000-0000-000000000001@first.example.com:443"
        "?security=tls&fp=unsafe&cs=TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256"
        "&type=xhttp&extra=%7B%22custom%22%3A%22one%22%7D"
        "#NodeOne"
    )
    link_two = (
        "vless://00000000-0000-0000-0000-000000000002@second.example.com:443" "?security=tls&fp=chrome" "#NodeTwo"
    )

    batch_payload = f"{link_one}\n{link_two}"
    items = LibXrayParserAdapter.parse_batch(batch_payload)
    assert len(items) == 2

    # Verify NodeOne
    ob1 = items[0]["outbound"]
    tls1 = ob1.get("streamSettings", {}).get("tlsSettings", {})
    xhttp1 = ob1.get("streamSettings", {}).get("xhttpSettings", {})
    assert tls1.get("fingerprint") == "unsafe"
    assert tls1.get("cipherSuites") == "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256"
    assert xhttp1.get("extra", {}).get("custom") == "one"

    # Verify NodeTwo does NOT inherit NodeOne settings
    ob2 = items[1]["outbound"]
    tls2 = ob2.get("streamSettings", {}).get("tlsSettings", {})
    xhttp2 = ob2.get("streamSettings", {}).get("xhttpSettings", {})
    assert tls2.get("fingerprint") == "chrome"
    assert "cipherSuites" not in tls2 or not tls2.get("cipherSuites")
    assert not xhttp2.get("extra")


def test_adapter_augment_preserves_encoded_percent_in_json():
    """Verify _augment_outbound_from_link does not double-decode percent escapes in extra JSON."""
    raw_link = (
        "vless://00000000-0000-0000-0000-000000000001@example.com:443"
        "?security=tls&type=xhttp"
        "&extra=%7B%22path%22%3A%22%252Fapi%22%7D"
        "#TestPercent"
    )
    ob = {
        "protocol": "vless",
        "streamSettings": {
            "security": "tls",
            "network": "xhttp",
        },
    }
    LibXrayParserAdapter._augment_outbound_from_link(ob, raw_link)
    extra = ob.get("streamSettings", {}).get("xhttpSettings", {}).get("extra", {})
    # Must preserve %2F literally without double-decoding into /
    assert extra.get("path") == "%2Fapi"


def test_adapter_parse_direct_xhttp_extra_parameters():
    """Verify direct query parameters for xHTTP are collected and nested under extra with xmux."""
    if not LibXrayParserAdapter.is_available():
        pytest.skip("xray-parser binary not built yet")

    link = (
        "vless://00000000-0000-0000-0000-000000000001@example.com:443"
        "?security=tls&type=xhttp&mode=auto"
        "&noSSEHeader=true&downloadProxy=true&xPaddingBytes=100-200"
        "&xmuxMaxConcurrency=16&xmuxMaxConnections=4"
        "#DirectXHTTP"
    )
    res = LibXrayParserAdapter.parse(link)
    xhttp = res["config"]["outbounds"][0]["streamSettings"]["xhttpSettings"]
    extra = xhttp.get("extra", {})

    assert extra.get("noSSEHeader") is True
    assert extra.get("downloadProxy") is True
    assert extra.get("xPaddingBytes") == "100-200"
    xmux = extra.get("xmux", {})
    assert xmux.get("maxConcurrency") == 16
    assert xmux.get("maxConnections") == 4


def test_adapter_parse_flat_finalmask_parameters():
    """Verify flat fm_tcp_* parameters are routed and preserved in binary parser output."""
    if not LibXrayParserAdapter.is_available():
        pytest.skip("xray-parser binary not built yet")

    link = (
        "vless://00000000-0000-0000-0000-000000000001@example.com:443"
        "?security=tls"
        "&fm_tcp_type=fragment&fm_tcp_packets=tlshello&fm_tcp_lengths=100-200&fm_tcp_delays=10-20"
        "#FlatFM"
    )
    res = LibXrayParserAdapter.parse(link)
    stream = res["config"]["outbounds"][0]["streamSettings"]
    finalmask = stream.get("finalmask", {})

    assert "tcp" in finalmask
    assert len(finalmask["tcp"]) == 1
    tcp_mask = finalmask["tcp"][0]
    assert tcp_mask["type"] == "fragment"
    assert tcp_mask["settings"]["packets"] == "tlshello"


def test_python_parser_validation_with_xray_core():
    """Verify configs generated purely by Python parsers are 100% valid in Xray-core engine."""
    if not LibXrayParserAdapter.is_available():
        pytest.skip("xray-parser binary not built yet")

    from src.core.parsers.vless import VlessParser

    test_link = (
        "vless://00000000-0000-0000-0000-000000000001@example.com:443"
        "?security=tls&alpn=h2&fp=unsafe"
        "&cs=TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256"
        "&type=xhttp&mode=auto&path=/test"
        "&extra=%7B%22noSSEHeader%22%3Atrue%2C%22downloadProxy%22%3Atrue%7D"
        "&fm=%7B%22tcp%22%3A%5B%7B%22type%22%3A%22fragment%22%2C"
        "%22settings%22%3A%7B%22packets%22%3A%22tlshello%22%2C%22lengths%22%3A%5B%22100-200%22%5D%2C"
        "%22delays%22%3A%5B%2210-20%22%5D%7D%7D%5D%7D"
        "#PythonVerifiedNode"
    )

    py_res = VlessParser.parse(test_link)
    cfg_to_validate = {
        "log": {"loglevel": "warning"},
        "inbounds": [],
        "outbounds": py_res["config"]["outbounds"],
    }
    is_valid, err = LibXrayParserAdapter.validate_config(cfg_to_validate)
    assert is_valid is True, f"Python parser output failed Xray validation: {err}"
