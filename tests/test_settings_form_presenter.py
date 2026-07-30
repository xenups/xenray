"""Comprehensive unit tests for SettingsFormPresenter."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.ui.components.settings.settings_form_presenter import SettingsFormPresenter


class TestSettingsFormPresenter(unittest.TestCase):
    """Test suite for SettingsFormPresenter form validation, boundary limits, and settings persistence."""

    def setUp(self):
        self.mock_context = MagicMock()
        self.mock_toast = MagicMock()
        self.presenter = SettingsFormPresenter(self.mock_context, self.mock_toast)

    def test_save_port_valid_boundary(self):
        # Lower bound
        success_min, _ = self.presenter.save_port("1024")
        self.assertTrue(success_min)
        self.mock_context.settings.set_proxy_port.assert_called_with(1024)

        # Upper bound
        success_max, _ = self.presenter.save_port("65535")
        self.assertTrue(success_max)
        self.mock_context.settings.set_proxy_port.assert_called_with(65535)

    def test_save_port_invalid_out_of_range(self):
        # Below lower bound
        success_low, err_low = self.presenter.save_port("1023")
        self.assertFalse(success_low)
        self.assertIn("invalid", err_low.lower())

        # Above upper bound
        success_high, err_high = self.presenter.save_port("65536")
        self.assertFalse(success_high)
        self.assertIn("invalid", err_high.lower())

    def test_save_port_invalid_non_integer(self):
        for invalid_input in ["abc", "10808.5", "", "   "]:
            success, err = self.presenter.save_port(invalid_input)
            self.assertFalse(success)

    def test_save_country(self):
        self.presenter.save_country("FI")
        self.mock_context.settings.set_routing_country.assert_called_with("FI")

        self.presenter.save_country("none")
        self.mock_context.settings.set_routing_country.assert_called_with("")

    def test_save_tun_engine(self):
        self.presenter.save_tun_engine("sing-box")
        self.mock_context.settings.set_tun_engine.assert_called_with("sing-box")

    def test_save_language(self):
        self.presenter.save_language("fa")
        self.mock_context.settings.set_language.assert_called_with("fa")

    def test_reset_close_preference(self):
        self.presenter.reset_close_preference()
        self.mock_context.settings.set_close_action.assert_called_with("")


if __name__ == "__main__":
    unittest.main()
