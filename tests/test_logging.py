"""Tests for strict 5 MB log rotation limits across the application."""

import logging
import logging.handlers
import sys
from unittest.mock import MagicMock, patch

from loguru import logger as loguru_logger
from loguru._file_sink import FileSink, Retention
from loguru._string_parsers import parse_size

from src.core.constants import LOG_BACKUP_COUNT, LOG_MAX_BYTES
from src.core.settings import Settings
from src.utils.log_utils import rotate_oversized_log_file
from src.utils.process_utils import ProcessUtils


def test_log_ceiling_is_exactly_5mb():
    """The rotation ceiling is exactly 5 * 1024 * 1024 bytes."""
    assert LOG_MAX_BYTES == 5 * 1024 * 1024
    assert LOG_BACKUP_COUNT == 3
    # loguru "5 MiB" maps to the exact binary ceiling used by RotatingFileHandler.
    assert parse_size("5 MiB") == LOG_MAX_BYTES


def test_central_logger_uses_strict_rotation():
    """The central xenray.log sink rotates at 5 MiB, keeps 3 files, utf-8."""
    sinks = [h._sink for h in loguru_logger._core.handlers.values() if isinstance(h._sink, FileSink)]
    assert sinks, "expected the central loguru file sink to be configured"
    sink = sinks[0]
    assert sink.encoding == "utf-8"
    assert sink._retention_function.func is Retention.retention_count
    assert sink._retention_function.keywords == {"number": LOG_BACKUP_COUNT}
    assert sink._rotation_function is not None


class TestRotateOversizedLogFile:
    """Tests for the raw subprocess-log rotation helper."""

    def test_small_file_is_not_touched(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text("small")
        rotate_oversized_log_file(str(log), max_bytes=1024, backup_count=3)
        assert log.read_text() == "small"
        assert not (tmp_path / "app.log.1").exists()

    def test_oversized_file_rotates_and_truncates(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text("x" * 2000)
        rotate_oversized_log_file(str(log), max_bytes=1024, backup_count=3)
        assert log.read_text() == ""
        assert (tmp_path / "app.log.1").read_text() == "x" * 2000

    def test_backups_shift_and_oldest_dropped(self, tmp_path):
        (tmp_path / "app.log.1").write_text("b1")
        (tmp_path / "app.log.2").write_text("b2")
        (tmp_path / "app.log.3").write_text("b3")
        (tmp_path / "app.log").write_text("z" * 2000)

        rotate_oversized_log_file(str(tmp_path / "app.log"), max_bytes=1024, backup_count=3)

        assert (tmp_path / "app.log").read_text() == ""
        assert (tmp_path / "app.log.1").read_text() == "z" * 2000
        assert (tmp_path / "app.log.2").read_text() == "b1"
        assert (tmp_path / "app.log.3").read_text() == "b2"
        assert not (tmp_path / "app.log.4").exists()


class TestRunCommandRotation:
    """run_command must rotate subprocess logs before opening them."""

    @patch("src.utils.process_utils.rotate_oversized_log_file")
    @patch("subprocess.Popen")
    @patch("src.platform.windows.process.WindowsProcessAdapter.get_subprocess_flags", return_value=0)
    @patch("src.platform.windows.process.WindowsProcessAdapter.get_startupinfo", return_value=None)
    def test_rotates_stdout_and_stderr_logs(self, mock_startup, mock_flags, mock_popen, mock_rotate):
        mock_popen.return_value = MagicMock()
        proc = ProcessUtils.run_command(["test", "cmd"], stdout_file="out.log", stderr_file="err.log")
        assert proc is not None
        mock_rotate.assert_any_call("out.log")
        mock_rotate.assert_any_call("err.log")


class TestSettingsLogging:
    """Settings.setup_logging must use a bounded RotatingFileHandler."""

    def test_setup_logging_uses_rotating_file_handler(self, tmp_path):
        log = str(tmp_path / "early.log")
        orig_stdout, orig_stderr = sys.stdout, sys.stderr
        tee = None
        try:
            Settings.setup_logging(log)
            tee = sys.stdout
            assert isinstance(tee.log, logging.handlers.RotatingFileHandler)
            assert tee.log.maxBytes == LOG_MAX_BYTES
            assert tee.log.backupCount == LOG_BACKUP_COUNT
            assert tee.log.encoding == "utf-8"

            # Writing past the ceiling triggers a rotation.
            tee.terminal = None  # avoid echoing to the real stdout
            tee.log.maxBytes = 32
            tee.write("x" * 64)
            assert (tmp_path / "early.log.1").exists()
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr
            if tee is not None and tee.log is not None:
                try:
                    tee.log.close()
                except Exception:
                    pass

    @patch("src.utils.log_utils.rotate_oversized_log_file")
    def test_create_log_files_rotates_subprocess_logs(self, mock_rotate):
        Settings.create_log_files()
        assert mock_rotate.call_count == 2
