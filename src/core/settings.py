"""Application settings."""
import os
import sys


class Settings:
    """Application settings and environment configuration."""
    
    def __init__(self):
        """Initialize settings."""
        from src.core.constants import APPDIR, XRAY_LOCATION_ASSET

        # Set Xray location asset environment variable
        os.environ['XRAY_LOCATION_ASSET'] = XRAY_LOCATION_ASSET
        
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
                self.log = open(logfile_path, "w", buffering=1)
            
            def write(self, message):
                self.terminal.write(message)
                self.log.write(message)
            
            def flush(self):
                self.terminal.flush()
                self.log.flush()
        
        sys.stdout = TeeOutput(log_file_path)
        sys.stderr = sys.stdout
    
    @staticmethod
    def create_temp_directories():
        """Create necessary temporary directories."""
        from src.core.constants import TEMP_ROOT
        
        os.makedirs(os.path.join(TEMP_ROOT, "usr", "bin"), exist_ok=True)
    
    @staticmethod
    def create_log_files():
        """Create/clear log files if they don't exist or are too large (>1MB)."""
        from src.core.constants import TUN_LOG_FILE, XRAY_LOG_FILE
        
        max_size = 1 * 1024 * 1024  # 1MB limit
        
        for log_file in [XRAY_LOG_FILE, TUN_LOG_FILE]:
            should_clear = False
            if not os.path.exists(log_file):
                should_clear = True
            elif os.path.getsize(log_file) > max_size:
                should_clear = True
            
            if should_clear:
                with open(log_file, "w") as f:
                    pass
