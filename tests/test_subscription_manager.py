import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.subscription_manager import SubscriptionManager


class TestSubscriptionManager:
    @pytest.fixture
    def mock_config_manager(self):
        return MagicMock()

    @pytest.fixture
    def sub_manager(self, mock_config_manager):
        return SubscriptionManager(mock_config_manager)

    def test_parse_plain_text(self, sub_manager):
        """Test parsing plain text links."""
        content = "vless://uuid@host:443?type=tcp#Server1\nvless://uuid2@host2:443?type=ws#Server2"
        profiles = sub_manager._parse_subscription_content(content)

        assert len(profiles) == 2
        assert profiles[0]["name"] == "Server1"
        assert profiles[1]["name"] == "Server2"

    def test_parse_base64(self, sub_manager):
        """Test parsing base64 encoded links."""
        raw_links = "vless://uuid@host:443?type=tcp#Server1\n"
        b64_content = base64.b64encode(raw_links.encode("utf-8")).decode("utf-8")

        profiles = sub_manager._parse_subscription_content(b64_content)
        assert len(profiles) == 1
        assert profiles[0]["name"] == "Server1"

    def test_parse_json(self, sub_manager):
        """Test parsing JSON subscription format."""
        json_data = [
            {
                "remarks": "JSON Server",
                "outbounds": [{"protocol": "vless"}],
                "tag": "proxy",
            }
        ]
        content = json.dumps(json_data)
        profiles = sub_manager._parse_subscription_content(content)

        assert len(profiles) == 1
        assert profiles[0]["name"] == "JSON Server"
        assert "config" in profiles[0]

    @patch("urllib.request.urlopen")
    def test_fetch_subscription(self, mock_urlopen, sub_manager):
        """Test fetching subscription from URL."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"vless://uuid@host:443#FetchedServer"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        profiles = sub_manager.fetch_subscription("http://example.com/sub")
        assert len(profiles) == 1
        assert profiles[0]["name"] == "FetchedServer"
        mock_urlopen.assert_called_once()

    def test_update_subscription(self, sub_manager, mock_config_manager):
        """Test update_subscription with threading and callback."""
        sub_id = "test-sub-id"
        mock_config_manager.load_subscriptions.return_value = [
            {
                "id": sub_id,
                "name": "My Sub",
                "url": "http://example.com/sub",
                "profiles": [],
            }
        ]

        # Mock fetch_subscription to return a list of profiles
        with patch.object(sub_manager, "fetch_subscription", return_value=[{"name": "New Profile"}]):
            callback_mock = MagicMock()

            # Start update (this runs in a thread)
            sub_manager.update_subscription(sub_id, callback=callback_mock)

            # Wait for thread to finish (it's very fast since it's all mocked)
            # A small sleep or polling would be better but let's try a small sleep
            time.sleep(0.1)

            from unittest.mock import ANY

            mock_config_manager.save_subscription_data.assert_called()
            callback_mock.assert_called_with(True, ANY)

    def test_update_subscription_not_found(self, sub_manager, mock_config_manager):
        """Test update_subscription when ID is not found."""
        mock_config_manager.load_subscriptions.return_value = []
        sub_manager.update_subscription("wrong-id")

        # Small wait for thread
        time.sleep(0.1)
        mock_config_manager.save_subscription_data.assert_not_called()
