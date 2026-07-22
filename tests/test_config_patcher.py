"""Tests for ConfigPatcher safe stream fallbacks."""
import pytest

from src.services.config_patcher import ConfigPatcher


@pytest.fixture
def patcher():
    return ConfigPatcher()


# ---------------------------------------------------------------------------
# _apply_stream_fallbacks — SNI tests
# ---------------------------------------------------------------------------


class TestApplyStreamFallbacksSni:
    """SNI fallback logic in ConfigPatcher._apply_stream_fallbacks()."""

    def test_sni_filled_for_tls_domain(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {"security": "tls"},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is True
        assert outbound["streamSettings"]["tlsSettings"]["serverName"] == "example.com"

    def test_sni_not_overridden_if_exists(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {
                "security": "tls",
                "tlsSettings": {"serverName": "custom.example.com"},
            },
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is False
        assert outbound["streamSettings"]["tlsSettings"]["serverName"] == "custom.example.com"

    def test_sni_skipped_for_ip_domain(self, patcher):
        outbound = {
            "protocol": "vmess",
            "settings": {"vnext": [{"address": "1.1.1.1", "port": 443}]},
            "streamSettings": {"security": "tls"},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "1.1.1.1")
        assert applied is False

    def test_reality_server_name_filled(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {"security": "reality"},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is True
        assert outbound["streamSettings"]["realitySettings"]["serverName"] == "example.com"

    def test_reality_server_name_not_overridden(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {
                "security": "reality",
                "realitySettings": {"serverName": "custom.example.com"},
            },
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is False
        assert outbound["streamSettings"]["realitySettings"]["serverName"] == "custom.example.com"

    def test_no_security_skips_sni(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {"security": "none"},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is False

    def test_stream_settings_created_if_missing(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is False  # no security set


# ---------------------------------------------------------------------------
# _apply_stream_fallbacks — Host header tests
# ---------------------------------------------------------------------------


class TestApplyStreamFallbacksHost:
    """Host header fallback logic."""

    def test_ws_host_filled(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {"network": "ws", "security": "none"},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is True
        assert outbound["streamSettings"]["wsSettings"]["headers"]["Host"] == "example.com"

    def test_ws_host_not_overridden(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {
                "network": "ws",
                "wsSettings": {"headers": {"Host": "custom.example.com"}},
            },
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is False
        assert outbound["streamSettings"]["wsSettings"]["headers"]["Host"] == "custom.example.com"

    def test_ws_host_skipped_for_ip(self, patcher):
        outbound = {
            "protocol": "vmess",
            "settings": {"vnext": [{"address": "1.1.1.1", "port": 443}]},
            "streamSettings": {"network": "ws", "security": "none"},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "1.1.1.1")
        assert applied is False

    def test_ws_headers_dict_created_if_missing(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {"network": "ws", "wsSettings": {}},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is True
        assert outbound["streamSettings"]["wsSettings"]["headers"]["Host"] == "example.com"

    def test_httpupgrade_host_filled(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {"network": "httpupgrade"},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is True
        assert outbound["streamSettings"]["httpupgradeSettings"]["host"] == "example.com"

    def test_httpupgrade_host_skipped_for_ip(self, patcher):
        outbound = {
            "protocol": "vmess",
            "settings": {"vnext": [{"address": "1.1.1.1", "port": 443}]},
            "streamSettings": {"network": "httpupgrade"},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "1.1.1.1")
        assert applied is False

    def test_xhttp_host_filled(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {"network": "xhttp"},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is True
        assert outbound["streamSettings"]["xhttpSettings"]["host"] == "example.com"

    def test_xhttp_host_skipped_for_ip(self, patcher):
        outbound = {
            "protocol": "vmess",
            "settings": {"vnext": [{"address": "1.1.1.1", "port": 443}]},
            "streamSettings": {"network": "xhttp"},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "1.1.1.1")
        # Host is skipped for IP, but mode is still defaulted to packet-up
        assert applied is True
        assert "host" not in outbound["streamSettings"]["xhttpSettings"]
        assert outbound["streamSettings"]["xhttpSettings"]["mode"] == "packet-up"

    def test_xhttp_mode_defaulted(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {"network": "xhttp"},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is True
        assert outbound["streamSettings"]["xhttpSettings"]["mode"] == "packet-up"

    def test_xhttp_mode_not_overridden(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {
                "network": "xhttp",
                "xhttpSettings": {"mode": "auto", "host": "already.set"},
            },
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        # Both host and mode are already set — no fallback needed
        assert applied is False
        assert outbound["streamSettings"]["xhttpSettings"]["mode"] == "auto"

    def test_unrecognized_network_skipped(self, patcher):
        outbound = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": "example.com", "port": 443}]},
            "streamSettings": {"network": "grpc"},
        }
        applied = patcher._apply_stream_fallbacks(outbound, "example.com")
        assert applied is False


# ---------------------------------------------------------------------------
# safe_patch() — integration
# ---------------------------------------------------------------------------


class TestSafePatch:
    """Tests for ConfigPatcher.safe_patch()."""

    def test_patches_supported_protocol(self, patcher):
        config = {
            "outbounds": [
                {
                    "protocol": "vless",
                    "settings": {"vnext": [{"address": "example.com", "port": 443}]},
                    "streamSettings": {"network": "tcp", "security": "tls"},
                }
            ]
        }
        patcher.safe_patch(config)
        assert config["outbounds"][0]["streamSettings"]["tlsSettings"]["serverName"] == "example.com"

    def test_skips_unsupported_protocol(self, patcher):
        config = {
            "outbounds": [
                {
                    "protocol": "unknown",
                    "settings": {"vnext": [{"address": "example.com", "port": 443}]},
                    "streamSettings": {"network": "tcp", "security": "tls"},
                }
            ]
        }
        patcher.safe_patch(config)
        assert "tlsSettings" not in config["outbounds"][0].get("streamSettings", {})

    def test_skips_missing_server_object(self, patcher):
        config = {
            "outbounds": [
                {
                    "protocol": "vless",
                    "settings": {},
                    "streamSettings": {"network": "tcp", "security": "tls"},
                }
            ]
        }
        patcher.safe_patch(config)  # should not raise

    def test_empty_outbounds(self, patcher):
        patcher.safe_patch({"outbounds": []})  # should not raise

    def test_missing_outbounds(self, patcher):
        patcher.safe_patch({})  # should not raise

    def test_patches_multiple_outbounds(self, patcher):
        config = {
            "outbounds": [
                {
                    "protocol": "vless",
                    "settings": {"vnext": [{"address": "a.com", "port": 443}]},
                    "streamSettings": {"network": "tcp", "security": "tls"},
                },
                {
                    "protocol": "trojan",
                    "settings": {"servers": [{"address": "b.com", "port": 443}]},
                    "streamSettings": {"network": "ws"},
                },
            ]
        }
        patcher.safe_patch(config)
        assert config["outbounds"][0]["streamSettings"]["tlsSettings"]["serverName"] == "a.com"
        assert config["outbounds"][1]["streamSettings"]["wsSettings"]["headers"]["Host"] == "b.com"
