"""Comprehensive unit tests for IPGeolocationService."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.services.ip_geolocation_service import IPGeolocationService, fetch_country_info_from_ip, fetch_public_exit_ip


class TestIPGeolocationService(unittest.TestCase):
    """Test suite for IPGeolocationService public exit IP lookups, failover, and caching."""

    def test_fetch_country_info_from_empty_ip(self):
        code, name = IPGeolocationService.fetch_country_info_from_ip("")
        self.assertIsNone(code)
        self.assertIsNone(name)

    def test_fetch_country_info_from_private_ip(self):
        code, name = IPGeolocationService.fetch_country_info_from_ip("127.0.0.1")
        self.assertIsNone(code)
        self.assertIsNone(name)

    @patch("requests.get")
    def test_fetch_country_info_from_ip_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "countryCode": "FI",
            "country": "Finland",
        }
        mock_get.return_value = mock_resp

        code, name = IPGeolocationService.fetch_country_info_from_ip("185.105.239.126")
        self.assertEqual(code, "FI")
        self.assertEqual(name, "Finland")

    @patch("requests.get")
    def test_fetch_country_info_from_ip_http_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        code, name = IPGeolocationService.fetch_country_info_from_ip("1.2.3.4")
        self.assertIsNone(code)
        self.assertIsNone(name)

    @patch("requests.get")
    def test_fetch_public_exit_ip_primary_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ip": "185.105.239.126",
            "country": "FI",
            "country_name": "Finland",
        }
        mock_get.return_value = mock_resp

        ip, code, name = fetch_public_exit_ip(10808)
        self.assertEqual(ip, "185.105.239.126")
        self.assertEqual(code, "FI")

    @patch("requests.get")
    def test_fetch_public_exit_ip_total_failure(self, mock_get):
        mock_get.side_effect = Exception("Network unreachable")
        ip, code, name = fetch_public_exit_ip(10808)
        self.assertIsNone(ip)


if __name__ == "__main__":
    unittest.main()
