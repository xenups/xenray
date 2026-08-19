"""Tests for admin_utils module."""

from unittest.mock import MagicMock, patch

import pytest
import typer

from src.utils.admin_utils import check_and_request_admin


class TestAdminUtils:
    def test_proxy_mode_no_admin_check(self):
        """Test that proxy mode doesn't check for admin."""
        with patch("src.utils.admin_utils.get_process_adapter") as mock_get_adapter:
            check_and_request_admin("proxy")
            mock_get_adapter.assert_not_called()

    def test_already_admin_returns_silently(self):
        """Test already admin returns without prompting."""
        mock_adapter = MagicMock()
        mock_adapter.is_elevated.return_value = True

        with patch("src.utils.admin_utils.get_process_adapter", return_value=mock_adapter):
            check_and_request_admin("vpn")
            mock_adapter.is_elevated.assert_called_once()
            mock_adapter.request_elevation.assert_not_called()

    def test_posix_not_admin_shows_hint_and_exits(self):
        """Test non-admin on POSIX (no interactive elevation) shows hint and exits."""
        mock_adapter = MagicMock()
        mock_adapter.is_elevated.return_value = False
        mock_adapter.supports_interactive_elevation.return_value = False
        mock_adapter.get_elevation_hint.return_value = "💡 Please run with sudo:\n   sudo run"

        with patch("src.utils.admin_utils.get_process_adapter", return_value=mock_adapter):
            with pytest.raises(typer.Exit) as exc:
                check_and_request_admin("vpn")
            assert exc.value.exit_code == 1

    @patch("sys.stdin.isatty", return_value=False)
    def test_windows_not_admin_no_tty(self, mock_tty):
        """Test non-admin and no TTY (CI/non-interactive) shows hint and exits."""
        mock_adapter = MagicMock()
        mock_adapter.is_elevated.return_value = False
        mock_adapter.supports_interactive_elevation.return_value = True
        mock_adapter.get_elevation_hint.return_value = "💡 Please run from an Administrator PowerShell/CMD"

        with patch("src.utils.admin_utils.get_process_adapter", return_value=mock_adapter):
            with pytest.raises(typer.Exit) as exc:
                check_and_request_admin("vpn")
            assert exc.value.exit_code == 1

    @patch("sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="y")
    def test_windows_elevation_success(self, mock_input, mock_tty):
        """Test elevation request success exits with 0."""
        mock_adapter = MagicMock()
        mock_adapter.is_elevated.return_value = False
        mock_adapter.supports_interactive_elevation.return_value = True
        mock_adapter.request_elevation.return_value = True

        with patch("src.utils.admin_utils.get_process_adapter", return_value=mock_adapter):
            with pytest.raises(typer.Exit) as exc:
                check_and_request_admin("vpn")
            assert exc.value.exit_code == 0
            mock_adapter.request_elevation.assert_called_once()

    @patch("sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="n")
    def test_windows_elevation_denied_by_user(self, mock_input, mock_tty):
        """Test elevation cancelled by user exits with 1."""
        mock_adapter = MagicMock()
        mock_adapter.is_elevated.return_value = False
        mock_adapter.supports_interactive_elevation.return_value = True

        with patch("src.utils.admin_utils.get_process_adapter", return_value=mock_adapter):
            with pytest.raises(typer.Exit) as exc:
                check_and_request_admin("vpn")
            assert exc.value.exit_code == 1
            mock_adapter.request_elevation.assert_not_called()

    @patch("sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="y")
    def test_windows_elevation_failed_or_cancelled(self, mock_input, mock_tty):
        """Test elevation failed exits with 1."""
        mock_adapter = MagicMock()
        mock_adapter.is_elevated.return_value = False
        mock_adapter.supports_interactive_elevation.return_value = True
        mock_adapter.request_elevation.return_value = False

        with patch("src.utils.admin_utils.get_process_adapter", return_value=mock_adapter):
            with pytest.raises(typer.Exit) as exc:
                check_and_request_admin("vpn")
            assert exc.value.exit_code == 1
