"""Tests for shared config utility functions."""

from src.services.config_utils import get_server_object, is_ip


class TestIsIp:
    """Tests for is_ip()."""

    def test_ipv4(self):
        assert is_ip("1.1.1.1") is True

    def test_ipv4_loopback(self):
        assert is_ip("127.0.0.1") is True

    def test_ipv4_private(self):
        assert is_ip("192.168.1.1") is True

    def test_ipv6(self):
        assert is_ip("2001:db8::1") is True

    def test_ipv6_loopback(self):
        assert is_ip("::1") is True

    def test_domain(self):
        assert is_ip("google.com") is False

    def test_localhost(self):
        assert is_ip("localhost") is False

    def test_empty_string(self):
        assert is_ip("") is False

    def test_ip_with_port_fails(self):
        assert is_ip("1.1.1.1:53") is False


class TestGetServerObject:
    """Tests for get_server_object()."""

    def test_vnext(self):
        settings = {"vnext": [{"address": "1.1.1.1", "port": 443}]}
        result = get_server_object(settings)
        assert result == {"address": "1.1.1.1", "port": 443}

    def test_servers(self):
        settings = {"servers": [{"address": "2.2.2.2", "port": 80}]}
        result = get_server_object(settings)
        assert result == {"address": "2.2.2.2", "port": 80}

    def test_vnext_takes_priority(self):
        settings = {
            "vnext": [{"address": "1.1.1.1", "port": 443}],
            "servers": [{"address": "2.2.2.2", "port": 80}],
        }
        result = get_server_object(settings)
        assert result["address"] == "1.1.1.1"

    def test_empty_vnext(self):
        settings = {"vnext": []}
        result = get_server_object(settings)
        assert result is None

    def test_empty_servers(self):
        settings = {"servers": []}
        result = get_server_object(settings)
        assert result is None

    def test_no_matching_keys(self):
        settings = {"other": [{"address": "1.1.1.1"}]}
        result = get_server_object(settings)
        assert result is None

    def test_empty_settings(self):
        result = get_server_object({})
        assert result is None

    def test_vnext_multiple_returns_first(self):
        settings = {
            "vnext": [
                {"address": "1.1.1.1", "port": 443},
                {"address": "2.2.2.2", "port": 80},
            ]
        }
        result = get_server_object(settings)
        assert result["address"] == "1.1.1.1"
