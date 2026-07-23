from unittest.mock import MagicMock, PropertyMock, patch

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
        mock_app_context = MagicMock()
        mock_app_context.profiles.load_all.return_value = []
        mock_init.return_value = (mock_app_context, MagicMock())

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No profiles found" in result.stdout

    @patch("src.cli._init_core")
    def test_list_profiles_with_data(self, mock_init):
        """Test list command with profiles."""
        mock_app_context = MagicMock()
        mock_app_context.profiles.load_all.return_value = [
            {"id": "1", "name": "Profile 1", "config": {"address": "1.2.3.4"}}
        ]
        mock_app_context.settings.get_last_selected_profile_id.return_value = None
        mock_init.return_value = (mock_app_context, MagicMock())

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
        mock_app_context = MagicMock()
        mock_app_context.profiles.load_all.return_value = [
            {"id": "1", "name": "Profile 1", "config": {"address": "1.2.3.4"}}
        ]
        mock_init.return_value = (mock_app_context, MagicMock())
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
        mock_app_context = MagicMock()
        mock_init.return_value = (mock_app_context, MagicMock())
        mock_parse.return_value = {
            "config": {"v": "2"},
            "name": "New Server",
            "protocol": "vless",
        }

        result = runner.invoke(app, ["add", "vless://test"])

        assert result.exit_code == 0
        assert "Profile added successfully!" in result.stdout
        mock_app_context.profiles.save.assert_called_with("New Server", {"v": "2"})

    @patch("src.cli._init_core")
    def test_disconnect_not_connected(self, mock_init):
        """Test disconnect when not connected."""
        mock_conn_mgr = MagicMock()
        mock_conn_mgr._current_connection = None
        mock_init.return_value = (MagicMock(), mock_conn_mgr)

        result = runner.invoke(app, ["disconnect"])

        assert result.exit_code == 0
        assert "Not connected" in result.stdout
        mock_conn_mgr.disconnect.assert_not_called()

    @patch("src.cli._init_core")
    def test_disconnect_connected(self, mock_init):
        """Test disconnect when connected."""
        mock_conn_mgr = MagicMock()
        mock_conn_mgr._current_connection = {"mode": "proxy"}
        mock_init.return_value = (MagicMock(), mock_conn_mgr)

        result = runner.invoke(app, ["disconnect"])

        assert result.exit_code == 0
        assert "Disconnected" in result.stdout
        mock_conn_mgr.disconnect.assert_called_once()

    @patch("src.cli._init_core")
    def test_status_disconnected(self, mock_init):
        """Test status when disconnected."""
        mock_conn_mgr = MagicMock()
        mock_conn_mgr._current_connection = None
        mock_init.return_value = (MagicMock(), mock_conn_mgr)

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "Disconnected" in result.stdout

    @patch("src.cli._init_core")
    def test_status_connected(self, mock_init):
        """Test status when connected."""
        mock_conn_mgr = MagicMock()
        mock_conn_mgr._current_connection = {"mode": "proxy"}
        mock_orch = MagicMock()
        type(mock_orch._xray_service).is_running = PropertyMock(return_value=True)
        mock_conn_mgr._orchestrator = mock_orch
        mock_init.return_value = (MagicMock(), mock_conn_mgr)

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "Connected" in result.stdout
        assert "proxy" in result.stdout

    @patch("src.cli._init_core")
    def test_status_inconsistent_state(self, mock_init):
        """Test status warning when xray is not running."""
        mock_conn_mgr = MagicMock()
        mock_conn_mgr._current_connection = {"mode": "vpn"}
        mock_orch = MagicMock()
        type(mock_orch._xray_service).is_running = PropertyMock(return_value=False)
        mock_conn_mgr._orchestrator = mock_orch
        mock_init.return_value = (MagicMock(), mock_conn_mgr)

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "inconsistent state" in result.stdout

    @patch("src.cli._init_core")
    @patch("src.services.connection_tester.ConnectionTester.test_connection_sync")
    def test_ping_single_success(self, mock_ping, mock_init):
        """Test single profile ping success."""
        mock_app_context = MagicMock()
        mock_app_context.profiles.load_all.return_value = [
            {"id": "1", "name": "Profile 1", "config": {"address": "1.2.3.4"}}
        ]
        mock_init.return_value = (mock_app_context, MagicMock())
        mock_ping.return_value = (
            True,
            "50ms",
            {"country_code": "DE", "country_name": "Germany", "city": "Berlin"},
        )

        result = runner.invoke(app, ["ping", "1"])

        assert result.exit_code == 0
        assert "Success!" in result.stdout
        assert "50ms" in result.stdout
        assert "Germany" in result.stdout

    @patch("src.cli._init_core")
    @patch("src.services.connection_tester.ConnectionTester.test_connection_sync")
    def test_ping_single_failure(self, mock_ping, mock_init):
        """Test single profile ping failure."""
        mock_app_context = MagicMock()
        mock_app_context.profiles.load_all.return_value = [
            {"id": "1", "name": "Profile 1", "config": {"address": "1.2.3.4"}}
        ]
        mock_init.return_value = (mock_app_context, MagicMock())
        mock_ping.return_value = (False, "Timeout", None)

        result = runner.invoke(app, ["ping", "1"])

        assert result.exit_code == 1
        assert "Failed: Timeout" in result.stdout

    @patch("src.cli._init_core")
    def test_ping_invalid_profile(self, mock_init):
        """Test ping with out-of-range profile number."""
        mock_app_context = MagicMock()
        mock_app_context.profiles.load_all.return_value = [
            {"id": "1", "name": "Profile 1", "config": {"address": "1.2.3.4"}}
        ]
        mock_init.return_value = (mock_app_context, MagicMock())

        result = runner.invoke(app, ["ping", "99"])

        assert result.exit_code == 1
        assert "not found" in result.stderr

    @patch("src.cli._init_core")
    @patch("src.services.connection_tester.ConnectionTester.test_connection_sync")
    def test_ping_batch_all(self, mock_ping, mock_init):
        """Test batch ping of all profiles."""
        mock_app_context = MagicMock()
        mock_app_context.profiles.load_all.return_value = [
            {"id": "1", "name": "Alpha", "config": {"address": "1.1.1.1"}},
            {"id": "2", "name": "Beta", "config": {"address": "2.2.2.2"}},
        ]
        mock_init.return_value = (mock_app_context, MagicMock())
        mock_ping.side_effect = [
            (True, "10ms", {"country_code": "US", "country_name": "USA", "city": "NY"}),
            (False, "Timeout", None),
        ]

        result = runner.invoke(app, ["ping"])

        assert result.exit_code == 0
        assert "Batch test" in result.stdout
        assert "Alpha" in result.stdout
        assert "Beta" in result.stdout
