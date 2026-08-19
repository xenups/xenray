"""Application settings."""

import logging
import logging.handlers
import os
import sys

from src.core.constants import LOG_BACKUP_COUNT, LOG_MAX_BYTES


class Settings:
    """Application settings and environment configuration."""

    def __init__(self):
        """Initialize settings."""
        from src.core.constants import APPDIR, XRAY_LOCATION_ASSET

        # Set Xray location asset environment variable
        os.environ["XRAY_LOCATION_ASSET"] = XRAY_LOCATION_ASSET

        # Store appdir for later use
        self.appdir = APPDIR

    @staticmethod
    def setup_logging(log_file_path: str):
        """
        Setup logging to both stdout and file.

        The file side uses a ``RotatingFileHandler`` with a strict 5 MB ceiling
        (``maxBytes = 5 * 1024 * 1024``) and ``backupCount = 3`` so the early-log
        file can never grow beyond 5 MB regardless of how much the process prints.

        Args:
            log_file_path: Path to log file
        """

        class TeeOutput:
            def __init__(self, logfile_path):
                self.terminal = sys.__stdout__
                self.log = None
                try:
                    self.log = logging.handlers.RotatingFileHandler(
                        logfile_path,
                        maxBytes=LOG_MAX_BYTES,
                        backupCount=LOG_BACKUP_COUNT,
                        encoding="utf-8",
                    )
                except Exception:
                    # If we can't open log file (e.g. locked by another instance),
                    # we proceed without file logging to avoid crash.
                    self.log = None

            def write(self, message):
                if self.terminal:
                    try:
                        self.terminal.write(message)
                    except Exception:
                        pass
                if self.log:
                    try:
                        stream = self.log.stream
                        if stream is not None:
                            # Rotate BEFORE writing if this message would push the
                            # file past the 5 MB ceiling (mirrors shouldRollover).
                            msg_bytes = len(message.encode("utf-8", errors="replace"))
                            if self.log.maxBytes > 0 and stream.tell() + msg_bytes >= self.log.maxBytes:
                                self.log.doRollover()
                                stream = self.log.stream  # re-fetch after rotation
                            if stream is not None:
                                stream.write(message)
                                stream.flush()
                    except Exception:
                        pass

            def flush(self):
                if self.terminal:
                    try:
                        self.terminal.flush()
                    except Exception:
                        pass
                if self.log:
                    try:
                        self.log.flush()
                    except Exception:
                        pass

        sys.stdout = TeeOutput(log_file_path)
        # Only redirect stderr if it exists (might be None in windowed mode)
        if sys.stderr:
            sys.stderr = sys.stdout

    @staticmethod
    def create_temp_directories():
        """Create necessary temporary directories."""
        from src.core.constants import TEMP_ROOT

        os.makedirs(os.path.join(TEMP_ROOT, "usr", "bin"), exist_ok=True)

    @staticmethod
    def create_log_files():
        """Sweep and purge/rotate any oversized log or backup files at startup.

        Enforces the 5 MB ceiling before a core binary is launched so leftover
        oversized logs or rotated backup files from previous sessions are purged.
        """
        from src.core.constants import SINGBOX_LOG_FILE, XRAY_LOG_FILE
        from src.utils.log_utils import cleanup_tmp_log_dir, rotate_oversized_log_file

        cleanup_tmp_log_dir()
        for log_file in [XRAY_LOG_FILE, SINGBOX_LOG_FILE]:
            rotate_oversized_log_file(log_file)
