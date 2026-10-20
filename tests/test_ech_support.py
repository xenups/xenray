"""Regression tests for ECH list resolution, echOutbound, and Xray configuration integration."""

from __future__ import annotations

import json
import urllib.parse
from unittest.mock import MagicMock, patch

import pytest

from src.core.ech_manager import EchListManager
from src.core.parsers.base import build_minimal_config
from src.core.parsers.binary_parser_adapter import LibXrayParserAdapter
from src.core.parsers.vless import VlessParser
from src.services.core_engines.xray_config_processor import XrayConfigProcessor

# Fully synthetic, structurally equivalent VLESS fixture with fabricated values
SYNTHETIC_ECH_OUTBOUND = {
    "tag": "tls-repack-dns",
    "protocol": "direct",
    "settings": {"redirect": "1.1.1.1:443"},
    "streamSettings": {
        "security": "tls",
        "tlsSettings": {
            "serverName": "www.example.com",
            "verifyPeerCertByName": "fromMitM,www.example.com",
            "alpn": ["fromMitM"],
            "fingerprint": "chrome",
        },
    },
}

SYNTHETIC_EXTRA = {
    "noSSEHeader": True,
    "downloadProxy": True,
    "uplinkHTTPMethod": "POST",
    "downlinkHTTPMethod": "GET",
    "xPaddingBytes": "100-1000",
    "scMaxEachGetBytes": 1048576,
    "scMaxEachPostBytes": 500000,
    "scMinPostsIntervalMs": 10,
    "headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.7204.100 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
    },
}

SYNTHETIC_ECH_FIXTURE = (
    "vless://00000000-0000-0000-0000-000000000001@server.example.org:443"
    "?encryption=none&security=tls&sni=sni.example.org"
    "&fp=chrome&alpn=h2%2Chttp%2F1.1&ech=h2c%3A%2F%2F1.1.1.1%2Fdns-query"
    f"&echOutbound={urllib.parse.quote(json.dumps(SYNTHETIC_ECH_OUTBOUND), safe='')}"
    "&type=xhttp&host=host.example.org&path=%2Fcalling&mode=auto"
    f"&extra={urllib.parse.quote(json.dumps(SYNTHETIC_EXTRA), safe='')}"
    "#Synthetic-ECH-Node"
)


class TestEchRegressionSuite:
    """Complete regression test suite matching Section 4 requirements."""

    def test_1_reference_uri_parsing_and_structure(self):
        """1. Synthetic reference URI with both ech and echOutbound parsed and validated."""
        result = VlessParser.parse(SYNTHETIC_ECH_FIXTURE)
        assert result["name"] == "Synthetic-ECH-Node"

        config = result["config"]
        outbounds = config["outbounds"]
        assert len(outbounds) == 4

        # Primary proxy outbound
        proxy_ob = outbounds[0]
        assert proxy_ob["protocol"] == "vless"
        assert proxy_ob["tag"] == "proxy"

        tls = proxy_ob["streamSettings"]["tlsSettings"]
        assert tls["echConfigList"] == "h2c://1.1.1.1/dns-query"
        assert tls["echSockopt"]["dialerProxy"] == "tls-repack-dns"
        assert tls["serverName"] == "sni.example.org"
        assert tls["alpn"] == ["h2", "http/1.1"]

        # echOutbound entry
        repack_ob = outbounds[1]
        assert repack_ob["tag"] == "tls-repack-dns"
        assert repack_ob["protocol"] == "direct"
        assert repack_ob["settings"]["redirect"] == "1.1.1.1:443"
        assert repack_ob["streamSettings"]["security"] == "tls"
        repack_tls = repack_ob["streamSettings"]["tlsSettings"]
        assert repack_tls["serverName"] == "www.example.com"
        assert repack_tls["verifyPeerCertByName"] == "fromMitM,www.example.com"
        assert repack_tls["alpn"] == ["fromMitM"]
        assert repack_tls["fingerprint"] == "chrome"

        # Fallback outbounds
        assert outbounds[2]["tag"] == "direct"
        assert outbounds[3]["tag"] == "block"

    def test_2_correct_decoding_of_ech_urls(self):
        """2. Correct decoding of ech URL variants without double-decoding or corruption."""
        variants = [
            "h2c://1.1.1.1/dns-query",
            "https://dns.google/dns-query",
            "udp://1.1.1.1",
            "example.com+https://1.1.1.1/dns-query",
            "AF7+DQBaAAAgACA51i3Ssu4wUMV4FNCc8iRX5J+YC4Bhigz9sacl2lCfSQ==",
        ]
        for v in variants:
            encoded_ech = urllib.parse.quote(v, safe="")
            link = (
                f"vless://00000000-0000-0000-0000-000000000001@server.example.com:443"
                f"?security=tls&ech={encoded_ech}#Node"
            )
            parsed = VlessParser.parse(link)
            tls = parsed["config"]["outbounds"][0]["streamSettings"]["tlsSettings"]
            assert tls["echConfigList"] == v

    def test_3_ech_outbound_json_decoding_and_field_preservation(self):
        """3. Correct JSON decoding and preservation of supported echOutbound fields."""
        outbound_data = {
            "tag": "custom-dns-repack",
            "protocol": "direct",
            "settings": {"redirect": "8.8.8.8:853"},
            "streamSettings": {
                "security": "tls",
                "tlsSettings": {
                    "serverName": "cloudflare-dns.com",
                    "verifyPeerCertByName": "fromMitM,cloudflare-dns.com",
                    "alpn": ["dot", "h2"],
                    "fingerprint": "firefox",
                },
            },
        }
        encoded_ob = urllib.parse.quote(json.dumps(outbound_data))
        link = (
            f"vless://00000000-0000-0000-0000-000000000001@server.example.com:443"
            f"?security=tls&ech=udp://1.1.1.1&echOutbound={encoded_ob}#Test"
        )
        parsed = VlessParser.parse(link)

        outbounds = parsed["config"]["outbounds"]
        repack = next(o for o in outbounds if o.get("tag") == "custom-dns-repack")
        assert repack == outbound_data

        # Ensure dialerProxy in primary outbound linked to the custom tag
        proxy_tls = outbounds[0]["streamSettings"]["tlsSettings"]
        assert proxy_tls["echSockopt"]["dialerProxy"] == "custom-dns-repack"

    def test_4_parameter_order_independence(self):
        """4. Equivalent parsing regardless of the order of ech and echOutbound query parameters."""
        ob_json = urllib.parse.quote(
            json.dumps({"tag": "dns-out", "protocol": "direct", "settings": {"redirect": "1.1.1.1:443"}})
        )
        ech_param = "ech=h2c%3A%2F%2F1.1.1.1%2Fdns-query"
        ob_param = f"echOutbound={ob_json}"

        link_order_1 = (
            f"vless://00000000-0000-0000-0000-000000000001@server.example.com:443"
            f"?security=tls&{ech_param}&{ob_param}#Node"
        )
        link_order_2 = (
            f"vless://00000000-0000-0000-0000-000000000001@server.example.com:443"
            f"?security=tls&{ob_param}&{ech_param}#Node"
        )

        res1 = VlessParser.parse(link_order_1)
        res2 = VlessParser.parse(link_order_2)

        assert res1["config"] == res2["config"]

    def test_5_malformed_percent_encoding(self):
        """5. Malformed percent-encoding detection."""
        malformed_links = [
            "vless://00000000-0000-0000-0000-000000000001@server.example.com:443?security=tls&ech=%ZZ#Node",
            "vless://00000000-0000-0000-0000-000000000001@server.example.com:443?security=tls&ech=%2#Node",
            "vless://00000000-0000-0000-0000-000000000001@server.example.com:443?security=tls&echOutbound=%G1#Node",
        ]
        for link in malformed_links:
            with pytest.raises(ValueError, match="Malformed percent-encoding"):
                VlessParser.parse(link)

    def test_6_malformed_ech_outbound_json(self):
        """6. Malformed echOutbound JSON raises actionable ValueError."""
        invalid_json_links = [
            (
                "vless://00000000-0000-0000-0000-000000000001@server.example.com:443"
                "?security=tls&echOutbound=not-json#Node"
            ),
            (
                "vless://00000000-0000-0000-0000-000000000001@server.example.com:443"
                "?security=tls&echOutbound=%7Binvalid-json#Node"
            ),
            (
                "vless://00000000-0000-0000-0000-000000000001@server.example.com:443"
                "?security=tls&echOutbound=12345#Node"
            ),
        ]
        for link in invalid_json_links:
            with pytest.raises(ValueError, match="Invalid echOutbound"):
                VlessParser.parse(link)

    def test_7_missing_or_invalid_outbound_fields(self):
        """7. Missing or invalid outbound tag/protocol/settings."""
        bad_outbounds = [
            {"protocol": "direct"},  # missing tag
            {"tag": "", "protocol": "direct"},  # empty tag
            {"tag": "dns-out"},  # missing protocol
            {"tag": "dns-out", "protocol": ""},  # empty protocol
            {"tag": "dns-out", "protocol": "direct", "settings": "invalid"},  # non-dict settings
            {"tag": "dns-out", "protocol": "direct", "streamSettings": ["bad"]},  # non-dict streamSettings
            {"tag": "proxy", "protocol": "direct"},  # tag collides with primary outbound
        ]
        for bad_ob in bad_outbounds:
            encoded = urllib.parse.quote(json.dumps(bad_ob))
            link = (
                f"vless://00000000-0000-0000-0000-000000000001@server.example.com:443"
                f"?security=tls&echOutbound={encoded}#Node"
            )
            with pytest.raises(ValueError, match="Invalid echOutbound"):
                VlessParser.parse(link)

    def test_8_duplicate_outbound_tags_and_repeated_processing(self):
        """8. Duplicate outbound tags and repeated profile imports."""
        # Parsing link with duplicate tag colliding with primary outbound raises ValueError
        colliding_ob = urllib.parse.quote(json.dumps({"tag": "proxy", "protocol": "direct"}))
        link = (
            f"vless://00000000-0000-0000-0000-000000000001@server.example.com:443"
            f"?security=tls&echOutbound={colliding_ob}#Node"
        )
        with pytest.raises(ValueError, match="collides with primary outbound tag"):
            VlessParser.parse(link)

        # build_minimal_config handles duplicate extra outbounds gracefully without duplication
        ob = {"tag": "proxy", "protocol": "vless"}
        extras = [
            {"tag": "dns-repack", "protocol": "direct"},
            {"tag": "dns-repack", "protocol": "direct"},  # Duplicate
        ]
        cfg = build_minimal_config(ob, extra_outbounds=extras)
        tags = [o.get("tag") for o in cfg["outbounds"]]
        assert tags.count("dns-repack") == 1

        # Repeated processing through XrayConfigProcessor does not duplicate outbounds
        app_ctx = MagicMock()
        app_ctx.settings.get_proxy_port.return_value = 10808
        app_ctx.settings.get_http_port.return_value = 10809
        app_ctx.settings.get_allow_lan.return_value = False
        app_ctx.settings.get_cipher_suites.return_value = ""
        app_ctx.settings.get_sni_spoof_enabled.return_value = False
        app_ctx.dns.load.return_value = []

        processor = XrayConfigProcessor(app_ctx)
        proc_config_1 = processor.process_config(cfg)
        proc_config_2 = processor.process_config(proc_config_1)

        tags_2 = [o.get("tag") for o in proc_config_2["outbounds"]]
        assert tags_2.count("dns-repack") == 1
        assert tags_2.count("direct") == 1
        assert tags_2.count("block") == 1

    def test_9_missing_unreachable_invalid_ech_list_source(self):
        """9. Missing, unreachable, or invalid ECH-list source."""
        mgr = EchListManager()

        # Missing / empty source
        with pytest.raises(ValueError, match="non-empty string"):
            mgr.fetch_ech_list("")

        # Unsupported scheme
        with pytest.raises(ValueError, match="Unsupported ECH-list source URL scheme"):
            mgr.fetch_ech_list("ftp://example.com/ech")

        # Unreachable network (mocked)
        with patch.object(mgr._session, "get", side_effect=Exception("Connection refused")):
            with pytest.raises(ValueError, match="ECH-list source unreachable"):
                mgr.fetch_ech_list("https://dns.example.com/dns-query")

        # Invalid response format (e.g. HTML or plain random string)
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>Not Found</body></html>"
        mock_resp.raise_for_status.return_value = None
        with patch.object(mgr._session, "get", return_value=mock_resp):
            with pytest.raises(ValueError, match="Failed to parse valid ECHConfigList"):
                mgr.fetch_ech_list("https://dns.example.com/dns-query")

    def test_10_correct_handling_of_valid_cache_after_failed_refresh(self):
        """10. Correct handling of valid cached data after a failed refresh."""
        mgr = EchListManager()
        source = "https://1.1.1.1/dns-query"
        valid_ech = "AEX+DQBBlQAgACCHfDGRwm701tQFkRzcNElNqe6ctrZhamT0rBClrYFnTAAEAAEAAQASY2xvdWRmbGFyZS1lY2guY29tAAA="

        # Step 1: Successful initial fetch caches the valid ECHConfigList
        mock_resp_success = MagicMock()
        mock_resp_success.text = json.dumps({"Answer": [{"type": 65, "data": f"1 . alpn=h2 ech={valid_ech}"}]})
        mock_resp_success.raise_for_status.return_value = None

        with patch.object(mgr._session, "get", return_value=mock_resp_success):
            resolved = mgr.fetch_ech_list(source, server_name="crypto.cloudflare.com")
            assert resolved == valid_ech
            assert mgr.get_cached(source, server_name="crypto.cloudflare.com") == valid_ech

        # Step 2: Failed refresh (e.g. 500 error or network outage)
        with patch.object(mgr._session, "get", side_effect=Exception("503 Service Unavailable")):
            refreshed = mgr.refresh(source, server_name="crypto.cloudflare.com")
            # Must return previously valid cached data without corrupting cache
            assert refreshed == valid_ech
            assert mgr.get_cached(source, server_name="crypto.cloudflare.com") == valid_ech

    def test_11_profiles_with_only_ech(self):
        """11. Profiles with only ech parameter."""
        link = (
            "vless://00000000-0000-0000-0000-000000000001@server.example.com:443"
            "?security=tls&ech=h2c%3A%2F%2F1.1.1.1%2Fdns-query#ECHOnly"
        )
        res = VlessParser.parse(link)
        outbounds = res["config"]["outbounds"]

        # Only proxy, direct, block
        assert len(outbounds) == 3
        tls = outbounds[0]["streamSettings"]["tlsSettings"]
        assert tls["echConfigList"] == "h2c://1.1.1.1/dns-query"
        assert "echSockopt" not in tls or "dialerProxy" not in tls.get("echSockopt", {})

    def test_12_profiles_with_only_ech_outbound(self):
        """12. Profiles with only echOutbound parameter."""
        ob_json = urllib.parse.quote(
            json.dumps({"tag": "repack", "protocol": "direct", "settings": {"redirect": "1.1.1.1:443"}})
        )
        link = (
            f"vless://00000000-0000-0000-0000-000000000001@server.example.com:443"
            f"?security=tls&echOutbound={ob_json}#ObOnly"
        )
        res = VlessParser.parse(link)
        outbounds = res["config"]["outbounds"]

        assert len(outbounds) == 4
        assert outbounds[0]["tag"] == "proxy"
        assert outbounds[1]["tag"] == "repack"
        assert outbounds[1]["protocol"] == "direct"

    def test_13_profiles_without_either_parameter(self):
        """13. Profiles without either parameter remain completely backward compatible."""
        link = (
            "vless://00000000-0000-0000-0000-000000000001@server.example.com:443"
            "?security=tls&sni=example.com&alpn=h2#Standard"
        )
        res = VlessParser.parse(link)
        outbounds = res["config"]["outbounds"]

        assert len(outbounds) == 3
        tls = outbounds[0]["streamSettings"]["tlsSettings"]
        assert "echConfigList" not in tls
        assert "echSockopt" not in tls

    def test_14_preservation_of_xhttp_extra_and_numeric_settings(self):
        """14. Preservation of XHTTP extra, including its headers and numeric settings."""
        result = VlessParser.parse(SYNTHETIC_ECH_FIXTURE)
        xhttp = result["config"]["outbounds"][0]["streamSettings"]["xhttpSettings"]
        assert "extra" in xhttp
        extra = xhttp["extra"]

        # Assert numeric and boolean properties
        assert extra["noSSEHeader"] is True
        assert extra["downloadProxy"] is True
        assert extra["uplinkHTTPMethod"] == "POST"
        assert extra["downlinkHTTPMethod"] == "GET"
        assert extra["xPaddingBytes"] == "100-1000"
        assert extra["scMaxEachGetBytes"] == 1048576
        assert extra["scMaxEachPostBytes"] == 500000
        assert extra["scMinPostsIntervalMs"] == 10

        # Assert headers dict preservation
        headers = extra["headers"]
        assert "User-Agent" in headers
        assert "Chrome/138" in headers["User-Agent"]
        assert headers["Accept"] == "*/*"
        assert headers["Connection"] == "keep-alive"

    def test_14b_malformed_extra_json_handling(self):
        """14b. Explicit test verifying that genuinely malformed extra JSON is handled safely."""
        malformed_extra_link = (
            "vless://00000000-0000-0000-0000-000000000001@server.example.org:443"
            "?security=tls&type=xhttp&extra=%7B%22scMinPostsIntervalMs%3A10%7D#Node"
        )
        result = VlessParser.parse(malformed_extra_link)
        xhttp = result["config"]["outbounds"][0]["streamSettings"]["xhttpSettings"]
        assert "extra" not in xhttp

    def test_15_runtime_xray_config_validation(self):
        """15. Correct final Xray configuration structure and successful runtime configuration validation."""
        result = VlessParser.parse(SYNTHETIC_ECH_FIXTURE)
        config = result["config"]

        # Validate via LibXrayParserAdapter using the installed Xray core
        is_valid, err_msg = LibXrayParserAdapter.validate_config(config)
        assert is_valid is True, f"Xray configuration validation failed: {err_msg}"
