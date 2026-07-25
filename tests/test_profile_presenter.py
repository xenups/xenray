"""Comprehensive unit tests for ProfilePresenter."""

from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from src.ui.helpers.profile_presenter import ProfilePresenter


class TestProfilePresenter(unittest.TestCase):
    """Test suite for ProfilePresenter metadata extraction, protocol detection, and DNS resolution."""

    def test_extract_profile_info_none(self):
        info = ProfilePresenter.extract_profile_info(None)
        self.assertEqual(info["protocol"], "Xray / VLESS")
        self.assertEqual(info["encryption"], "")
        self.assertEqual(info["latency"], "--")
        self.assertEqual(info["server_ip"], "--")
        self.assertEqual(info["country_code"], "")
        self.assertEqual(info["country_name"], "")

    def test_extract_profile_info_empty_dict(self):
        info = ProfilePresenter.extract_profile_info({})
        self.assertEqual(info["protocol"], "Xray / VLESS")
        self.assertEqual(info["encryption"], "")
        self.assertEqual(info["server_ip"], "--")

    def test_extract_profile_info_numerical_ipv4(self):
        prof = {
            "id": "1",
            "name": "Direct IPv4 Node",
            "address": "185.105.239.126",
            "port": 443,
            "protocol": "vless",
            "last_latency_val": 45,
            "country_code": "FI",
            "country_name": "Finland",
        }
        info = ProfilePresenter.extract_profile_info(prof)
        self.assertEqual(info["server_ip"], "185.105.239.126")
        self.assertEqual(info["latency"], "45ms")
        self.assertEqual(info["country_code"], "FI")
        self.assertEqual(info["country_name"], "Finland")

    def test_extract_profile_info_exit_ip_override(self):
        prof = {
            "id": "2",
            "name": "CDN Node",
            "address": "cf-node.example.com",
            "exit_ip": "89.163.220.10",
        }
        info = ProfilePresenter.extract_profile_info(prof)
        self.assertEqual(info["server_ip"], "89.163.220.10")

    @patch("socket.gethostbyname")
    def test_resolve_server_ip_domain_success(self, mock_dns):
        mock_dns.return_value = "1.1.1.1"
        ip = ProfilePresenter.resolve_server_ip("one.one.one.one")
        self.assertEqual(ip, "1.1.1.1")

    @patch("socket.gethostbyname")
    def test_resolve_server_ip_domain_gaierror(self, mock_dns):
        mock_dns.side_effect = socket.gaierror("Name or service not known")
        ip = ProfilePresenter.resolve_server_ip("invalid-domain-name.xyz")
        self.assertIn("invalid-domain-name.xyz", ip)

    def test_resolve_server_ip_direct(self):
        ip = ProfilePresenter.resolve_server_ip("8.8.8.8")
        self.assertEqual(ip, "8.8.8.8")


if __name__ == "__main__":
    unittest.main()
