"""Application settings."""
import os
import sys


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

        Args:
            log_file_path: Path to log file
        """

        class TeeOutput:
            def __init__(self, logfile_path):
                self.terminal = sys.__stdout__
                self.log = None
                try:
                    self.log = open(logfile_path, "w", buffering=1)
                except Exception:
                    # If we can't open log file (e.g. locked by another instance),
                    # we proceed without file logging to avoid crash.
                    pass

            def write(self, message):
                if self.terminal:
                    try:
                        self.terminal.write(message)
                    except Exception:
                        pass
                if self.log:
                    try:
                        self.log.write(message)
                    except Exception:
                        pass

            def flush(self):
                if self.terminal:
                    try:
                        self.terminal.flush()
                    except Exception:
                        pass
                if self.log:
                    self.log.flush()

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
        """Create/clear log files if they don't exist or are too large (>1MB)."""
        from src.core.constants import XRAY_LOG_FILE

        max_size = 1 * 1024 * 1024  # 1MB limit

        for log_file in [XRAY_LOG_FILE]:
            should_clear = False
            if not os.path.exists(log_file):
                should_clear = True
            elif os.path.getsize(log_file) > max_size:
                should_clear = True

            if should_clear:
                with open(log_file, "w"):
                    pass
