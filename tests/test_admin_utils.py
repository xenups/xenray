from unittest.mock import patch

import pytest
import typer

from src.utils.admin_utils import check_and_request_admin


class TestAdminUtils:
    def test_proxy_mode_no_admin_check(self):
        """Test that proxy mode doesn't check for admin."""
        with patch("src.utils.platform_utils.PlatformUtils.get_platform") as mock_plat:
            check_and_request_admin("proxy")
            mock_plat.assert_not_called()

    @patch("src.utils.platform_utils.PlatformUtils.get_platform")
    @patch("ctypes.windll.shell32.IsUserAnAdmin")
    def test_windows_already_admin(self, mock_is_admin, mock_plat):
        """Test Windows already admin."""
        mock_plat.return_value = "windows"
        mock_is_admin.return_value = 1

        check_and_request_admin("vpn")
        # Should return silently

    @patch("src.utils.platform_utils.PlatformUtils.get_platform")
    @patch("os.geteuid", create=True)
    def test_unix_already_admin(self, mock_geteuid, mock_plat):
        """Test Unix already admin."""
        mock_plat.return_value = "linux"
        mock_geteuid.return_value = 0

        check_and_request_admin("vpn")
        # Should return silently

    @patch("src.utils.platform_utils.PlatformUtils.get_platform")
    @patch("os.geteuid", create=True)
    def test_unix_not_admin(self, mock_geteuid, mock_plat):
        """Test Unix not admin - should show sudo message and exit."""
        mock_plat.return_value = "linux"
        mock_geteuid.return_value = 1000

        with pytest.raises(typer.Exit):
            check_and_request_admin("vpn")

    @patch("src.utils.platform_utils.PlatformUtils.get_platform")
    @patch("ctypes.windll.shell32.IsUserAnAdmin")
    @patch("sys.stdin.isatty")
    def test_windows_not_admin_no_tty(self, mock_tty, mock_is_admin, mock_plat):
        """Test Windows not admin and no TTY (CI/non-interactive)."""
        mock_plat.return_value = "windows"
        mock_is_admin.return_value = 0
        mock_tty.return_value = False

        with pytest.raises(typer.Exit):
            check_and_request_admin("vpn")

    @patch("src.utils.platform_utils.PlatformUtils.get_platform")
    @patch("ctypes.windll.shell32.IsUserAnAdmin")
    @patch("sys.stdin.isatty")
    @patch("builtins.input")
    @patch("ctypes.windll.shell32.ShellExecuteW")
    def test_windows_elevation_success(self, mock_execute, mock_input, mock_tty, mock_is_admin, mock_plat):
        """Test Windows elevation request success."""
        mock_plat.return_value = "windows"
        mock_is_admin.return_value = 0
        mock_tty.return_value = True
        mock_input.return_value = "y"
        mock_execute.return_value = 42  # Success code (>32)

        with pytest.raises(typer.Exit) as exc:
            check_and_request_admin("vpn")
        assert exc.value.exit_code == 0

    @patch("src.utils.platform_utils.PlatformUtils.get_platform")
    @patch("ctypes.windll.shell32.IsUserAnAdmin")
    @patch("sys.stdin.isatty")
    @patch("builtins.input")
    def test_windows_elevation_denied(self, mock_input, mock_tty, mock_is_admin, mock_plat):
        """Test Windows elevation request denied by user."""
        mock_plat.return_value = "windows"
        mock_is_admin.return_value = 0
        mock_tty.return_value = True
        mock_input.return_value = "n"

        with pytest.raises(typer.Exit) as exc:
            check_and_request_admin("vpn")
        assert exc.value.exit_code == 1
