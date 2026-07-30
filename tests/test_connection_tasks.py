"""Unit tests for ConnectionTasks."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.ui.handlers.tasks.connection_tasks import ConnectionTasks


class TestConnectionTasks(unittest.TestCase):
    """Test suite for ConnectionTasks location IP lookup and UI callback invocation."""

    @patch("src.ui.handlers.tasks.connection_tasks.fetch_public_exit_ip")
    def test_fetch_location_ip_task_success(self, mock_fetch):
        mock_fetch.return_value = ("185.105.239.126", "FI", "Finland")

        profile = {"id": "1", "name": "Finland Node"}
        mock_mw = MagicMock()
        mock_ui_call = MagicMock(side_effect=lambda fn: fn())

        ConnectionTasks.fetch_location_ip_task(
            proxy_port=10808,
            profile=profile,
            get_main_window_fn=lambda: mock_mw,
            ui_call_fn=mock_ui_call,
        )

        self.assertEqual(profile["exit_ip"], "185.105.239.126")
        self.assertEqual(profile["country_code"], "FI")
        self.assertEqual(profile["country_name"], "Finland")
        self.assertEqual(mock_mw._current_exit_ip, "185.105.239.126")
        mock_mw._update_selected_profile_ui.assert_called_with(profile)

    @patch("src.ui.handlers.tasks.connection_tasks.fetch_public_exit_ip")
    def test_fetch_location_ip_task_failure(self, mock_fetch):
        mock_fetch.return_value = (None, "", "")

        profile = {"id": "2", "name": "Failed Node"}
        mock_mw = MagicMock()
        mock_ui_call = MagicMock(side_effect=lambda fn: fn())

        ConnectionTasks.fetch_location_ip_task(
            proxy_port=10808,
            profile=profile,
            get_main_window_fn=lambda: mock_mw,
            ui_call_fn=mock_ui_call,
        )

        self.assertIsNone(mock_mw._current_exit_ip)


if __name__ == "__main__":
    unittest.main()
