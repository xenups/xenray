import subprocess
from unittest.mock import MagicMock, patch

from src.utils.process_utils import ProcessUtils


class TestProcessUtils:
    @patch("psutil.pid_exists")
    def test_is_running(self, mock_exists):
        """Test is_running check."""
        mock_exists.return_value = True
        assert ProcessUtils.is_running(1234) is True

        mock_exists.return_value = False
        assert ProcessUtils.is_running(5678) is False

    @patch("src.utils.process_utils.os.name", "nt")
    @patch("ctypes.windll.shell32.IsUserAnAdmin")
    def test_is_admin_windows(self, mock_is_admin):
        """Test is_admin on Windows."""
        mock_is_admin.return_value = 1
        assert ProcessUtils.is_admin() is True

        mock_is_admin.return_value = 0
        assert ProcessUtils.is_admin() is False

    @patch("src.utils.process_utils.os.name", "posix")
    @patch("os.geteuid", create=True)
    def test_is_admin_posix(self, mock_geteuid):
        """Test is_admin on POSIX."""
        mock_geteuid.return_value = 0
        assert ProcessUtils.is_admin() is True

        mock_geteuid.return_value = 1000
        assert ProcessUtils.is_admin() is False

    @patch("psutil.Process")
    @patch("psutil.pid_exists")
    def test_kill_process(self, mock_exists, mock_process_cls):
        """Test killing a process."""
        mock_exists.return_value = True
        mock_process = MagicMock()
        mock_process_cls.return_value = mock_process

        # Test terminate
        assert ProcessUtils.kill_process(1234, force=False) is True
        mock_process.terminate.assert_called_once()

        # Test kill
        assert ProcessUtils.kill_process(1234, force=True) is True
        mock_process.kill.assert_called_once()

    @patch("subprocess.Popen")
    @patch("src.utils.platform_utils.PlatformUtils.get_subprocess_flags")
    @patch("src.utils.platform_utils.PlatformUtils.get_startupinfo")
    def test_run_command(self, mock_startup, mock_flags, mock_popen):
        """Test running a command."""
        mock_popen.return_value = MagicMock()

        proc = ProcessUtils.run_command(["test", "cmd"])
        assert proc is not None
        mock_popen.assert_called_with(
            ["test", "cmd"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            creationflags=mock_flags.return_value,
            startupinfo=mock_startup.return_value,
        )

    @patch("subprocess.Popen")
    @patch("src.utils.platform_utils.PlatformUtils.get_subprocess_flags")
    @patch("src.utils.platform_utils.PlatformUtils.get_startupinfo")
    def test_run_command_sync(self, mock_startup, mock_flags, mock_popen):
        """Test running a command synchronously."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("out", "err")
        mock_popen.return_value = mock_proc

        result = ProcessUtils.run_command_sync(["test", "sync"])
        assert result == ("out", "err")

    @patch("psutil.Process")
    @patch("os.getpid")
    def test_kill_process_tree(self, mock_getpid, mock_process_cls):
        """Test killing a process tree."""
        mock_getpid.return_value = 100
        mock_parent = MagicMock()
        mock_child = MagicMock()
        mock_parent.children.return_value = [mock_child]
        mock_process_cls.return_value = mock_parent

        ProcessUtils.kill_process_tree(100)
        mock_child.kill.assert_called_once()
        mock_parent.kill.assert_called_once()
