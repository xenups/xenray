from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from src.cli import app

runner = CliRunner()


class TestCLI:
    @patch("src.cli._init_core")
    def test_version(self, mock_init):
        """Test version command."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "XenRay CLI v" in result.stdout

    @patch("src.cli._init_core")
    def test_list_profiles_empty(self, mock_init):
        """Test list command with no profiles."""
        mock_config_mgr = MagicMock()
        mock_config_mgr.load_profiles.return_value = []
        mock_init.return_value = (mock_config_mgr, MagicMock())

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No profiles found" in result.stdout

    @patch("src.cli._init_core")
    def test_list_profiles_with_data(self, mock_init):
        """Test list command with profiles."""
        mock_config_mgr = MagicMock()
        mock_config_mgr.load_profiles.return_value = [
            {"id": "1", "name": "Profile 1", "config": {"address": "1.2.3.4"}}
        ]
        mock_config_mgr.get_last_selected_profile_id.return_value = None
        mock_init.return_value = (mock_config_mgr, MagicMock())

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Profile 1" in result.stdout
        assert "1.2.3.4" in result.stdout

    @patch("src.cli._init_core")
    @patch("src.utils.admin_utils.check_and_request_admin")
    @patch("src.cli._prepare_config_file", return_value="temp.json")
    @patch("src.cli._cleanup_temp_file")
    @patch("src.cli._perform_connection")
    @patch("src.services.connection_tester.ConnectionTester.test_connection_sync")
    def test_connect_success(self, mock_ping, mock_perf, mock_cleanup, mock_prep, mock_admin, mock_init):
        """Test successful connect command."""
        mock_config_mgr = MagicMock()
        mock_config_mgr.load_profiles.return_value = [
            {"id": "1", "name": "Profile 1", "config": {"address": "1.2.3.4"}}
        ]
        mock_init.return_value = (mock_config_mgr, MagicMock())
        mock_perf.return_value = True
        mock_ping.return_value = (
            True,
            "100ms",
            {"country_code": "US", "country_name": "USA", "city": "NY"},
        )

        result = runner.invoke(app, ["connect", "1"])

        assert result.exit_code == 0
        assert "Connected successfully!" in result.stdout
        assert "Latency: 100ms" in result.stdout
        mock_perf.assert_called_once()

    @patch("src.cli._init_core")
    @patch("src.utils.link_parser.LinkParser.parse_link")
    def test_add_profile(self, mock_parse, mock_init):
        """Test add command."""
        mock_config_mgr = MagicMock()
        mock_init.return_value = (mock_config_mgr, MagicMock())
        mock_parse.return_value = {
            "config": {"v": "2"},
            "name": "New Server",
            "protocol": "vless",
        }

        result = runner.invoke(app, ["add", "vless://test"])

        assert result.exit_code == 0
        assert "Profile added successfully!" in result.stdout
        mock_config_mgr.save_profile.assert_called_with("New Server", {"v": "2"})
