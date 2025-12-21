from unittest.mock import MagicMock, patch

from src.services.geoip_service import GeoIPService


class TestGeoIPService:
    @patch("requests.get")
    def test_get_country_success(self, mock_get):
        """Test successful GeoIP lookup."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "countryCode": "DE",
            "country": "Germany",
            "city": "Berlin",
        }
        mock_get.return_value = mock_response

        result = GeoIPService.get_country()
        assert result["country_code"] == "DE"
        assert result["country_name"] == "Germany"
        assert result["city"] == "Berlin"

    @patch("requests.get")
    def test_get_country_fail_status(self, mock_get):
        """Test GeoIP lookup with 'fail' status in JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "fail"}
        mock_get.return_value = mock_response

        result = GeoIPService.get_country()
        assert result is None

    @patch("requests.get")
    def test_get_country_http_error(self, mock_get):
        """Test GeoIP lookup with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = GeoIPService.get_country()
        assert result is None

    @patch("requests.get")
    def test_get_country_exception(self, mock_get):
        """Test GeoIP lookup with connection exception."""
        mock_get.side_effect = Exception("Connection Refused")

        result = GeoIPService.get_country()
        assert result is None
