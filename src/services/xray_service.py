"""Xray service for managing Xray process."""
import os
from typing import Optional

from src.core.constants import APPDIR, XRAY_EXECUTABLE, XRAY_LOG_FILE
from src.utils.process_utils import ProcessUtils


class XrayService:
    """Service for managing Xray process."""
    
    def __init__(self):
        """Initialize Xray service."""
        self._process = None
        self._pid: Optional[int] = None
    
    def start(self, config_file_path: str) -> Optional[int]:
        """
        Start Xray with the given configuration.
        
        Args:
            config_file_path: Path to Xray configuration file
            
        Returns:
            Process ID or None if start failed
        """
        from src.core.logger import logger
        
        logger.debug(f"[XrayService] Starting Xray with config: {config_file_path}")
        
        if not os.path.isfile(config_file_path):
            logger.error(f"[XrayService] Config not found: {config_file_path}")
            return None
        
        # Small delay to ensure previous instance is fully terminated
        import time
        time.sleep(0.2)
        
        cmd = [
            XRAY_EXECUTABLE,
            "run",
            "-c",
            config_file_path
        ]
        
        logger.debug(f"[XrayService] Executing command: {' '.join(cmd)}")
        logger.debug(f"[XrayService] Log file: {XRAY_LOG_FILE}")
        
        self._process = ProcessUtils.run_command(
            cmd,
            stdout_file=XRAY_LOG_FILE,
            stderr_file=XRAY_LOG_FILE
        )
        
        if self._process:
            self._pid = self._process.pid
            logger.info(f"[XrayService] Started with PID {self._pid}")
            return self._pid
        else:
            logger.error("[XrayService] Failed to start process")
            return None
    
    def stop(self) -> bool:
        """
        Stop Xray process.
        
        Returns:
            True if successful, False otherwise
        """
        if not self._pid:
            return True
        
        success = ProcessUtils.kill_process(self._pid, force=False)
        
        if not success:
            # Try force kill
            success = ProcessUtils.kill_process(self._pid, force=True)
        
        if success:
            # Wait briefly for process to terminate (non-blocking)
            import time
            for _ in range(3):  # 300ms max wait
                if not ProcessUtils.is_running(self._pid):
                    break
                time.sleep(0.1)
            
            from src.core.logger import logger
            logger.info("[XrayService] Stopped")
            self._pid = None
            self._process = None
        
        return success
    
    def is_running(self) -> bool:
        """Check if Xray is running."""
        if not self._pid:
            return False
        return ProcessUtils.is_running(self._pid)
    
    @property
    def pid(self) -> Optional[int]:
        """Get Xray process ID."""
        return self._pid
