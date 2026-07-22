from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.services.xray_service import XrayService


class TestXrayService:
    @pytest.fixture
    def xray_service(self):
        with patch("src.utils.process_utils.ProcessUtils.is_running", return_value=False):
            return XrayService()

    @patch("src.utils.process_utils.ProcessUtils.run_command")
    @patch("os.path.isfile", return_value=True)
    @patch("builtins.open", new_callable=mock_open)
    def test_start_success(self, mock_file, mock_isfile, mock_run, xray_service):
        """Test starting Xray successfully."""
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_run.return_value = mock_proc

        pid = xray_service.start("config.json")

        assert pid == 1234
        assert xray_service.pid == 1234
        mock_run.assert_called_once()
        # Verify PID file was written
        mock_file().write.assert_called_with("1234")

    @patch("src.utils.process_utils.ProcessUtils.is_running", return_value=False)
    @patch("src.utils.process_utils.ProcessUtils.kill_process")
    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data="1234"))
    def test_stop_success(self, mock_exists, mock_kill, mock_is_running, xray_service):
        """Test stopping Xray."""
        xray_service._pid = 1234
        mock_kill.return_value = True

        with patch("os.remove") as mock_remove:
            assert xray_service.stop() is True
            assert xray_service.pid is None
            mock_kill.assert_called_with(1234, force=False)
            mock_remove.assert_called()
