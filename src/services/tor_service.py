"""Tor service for managing the Tor process."""
import os
import subprocess
import time
from typing import Optional

from src.core.constants import TOR_EXECUTABLE, TOR_LOG_FILE, TOR_PID_FILE, TOR_DATA_DIR, TMPDIR
from src.core.logger import logger
from src.utils.process_utils import ProcessUtils

# Constants
PROCESS_START_DELAY = 0.5  # seconds
STOP_CHECK_RETRIES = 5
STOP_CHECK_DELAY = 0.2

class TorService:
    """Service for managing the Tor process."""

    def __init__(self):
        """Initialize Tor service."""
        self._process = None
        self._pid: Optional[int] = None
        self._check_and_restore_pid()

    def _check_and_restore_pid(self):
        """Restore PID from file if it's still running."""
        if os.path.exists(TOR_PID_FILE):
            try:
                with open(TOR_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    self._pid = old_pid
                    logger.debug(f"[TorService] Restored PID {self._pid} from file")
            except Exception:
                pass

    def _cleanup_previous_instance(self):
        """Kill any existing Tor instance."""
        if os.path.exists(TOR_PID_FILE):
            try:
                with open(TOR_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    logger.info(f"[TorService] Found orphan process {old_pid}, killing...")
                    ProcessUtils.kill_process(old_pid, force=True)
                os.remove(TOR_PID_FILE)
            except Exception as e:
                logger.warning(f"[TorService] Failed to cleanup old PID file: {e}")

    def start(self, socks_port: int = 9050, use_bridges: str = "always") -> Optional[int]:
        """
        Start Tor process with Connection Assist (auto-fallback to bridges).
        
        Args:
            socks_port: SOCKS port for Tor to listen on
            use_bridges: Bridge mode - "auto" (try direct, fallback to bridges), 
                        "always" (always use bridges), "never" (direct only)
        
        Returns:
            Process ID if successful, None otherwise
        """
        # For censored regions, always use bridges by default
        if use_bridges == "always":
            logger.info("[TorService] Starting with bridges (always mode)...")
            return self._start_tor_internal(socks_port, use_bridges=True)
        
        # Auto mode: try direct first, then bridges if that fails
        elif use_bridges == "auto":
            logger.info("[TorService] Connection Assist: Trying direct connection first...")
            pid = self._start_tor_internal(socks_port, use_bridges=False)
            
            if pid:
                # Wait a bit and check if Tor is making progress
                import time
                time.sleep(5)
                progress, _ = self.get_bootstrap_progress()
                
                if progress >= 10:  # Making progress with direct connection
                    logger.info(f"[TorService] Direct connection working ({progress}%)")
                    return pid
                else:
                    # Direct connection seems blocked, retry with bridges
                    logger.warning("[TorService] Direct connection blocked, falling back to bridges...")
                    self.stop()
                    return self._start_tor_internal(socks_port, use_bridges=True)
            else:
                # Direct start failed, try with bridges
                logger.warning("[TorService] Direct start failed, trying with bridges...")
                return self._start_tor_internal(socks_port, use_bridges=True)
        
        elif use_bridges == "always":
            return self._start_tor_internal(socks_port, use_bridges=True)
        else:  # "never"
            return self._start_tor_internal(socks_port, use_bridges=False)

    def _start_tor_internal(self, socks_port: int, use_bridges: bool) -> Optional[int]:
        """Internal method to start Tor with specific bridge setting."""
        self._cleanup_previous_instance()
        
        # Ensure data directory exists
        os.makedirs(TOR_DATA_DIR, exist_ok=True)

        logger.info(f"[TorService] Starting Tor on port {socks_port}...")
        logger.info(f"[TorService] Executable: {TOR_EXECUTABLE}")
        logger.info(f"[TorService] Data dir: {TOR_DATA_DIR}")
        logger.info(f"[TorService] Using bridges: {use_bridges}")
        
        # Initialize config list
        config = []
        config.append(f"SocksPort {socks_port}")
        config.append(f"DataDirectory {TOR_DATA_DIR}")
        
        # Add geoip configuration
        bin_dir = os.path.dirname(TOR_EXECUTABLE)
        data_dir = os.path.join(bin_dir, "data")
        # Current directory structure:
        # data_dir = .../bin/tor_data (or temp dir)
        # pt_dir = TMPDIR/tor_pt (moving out of bin/ to avoid permission issues completely)
        pt_dir = os.path.join(TMPDIR, "tor_pt")
        
        geoip_path = os.path.join(data_dir, "geoip")
        geoip6_path = os.path.join(data_dir, "geoip6")
        
        if os.path.exists(geoip_path):
            config.append(f"GeoIPFile {geoip_path}")
        if os.path.exists(geoip6_path):
            config.append(f"GeoIPv6File {geoip6_path}")

        # Add bridge configuration for censorship circumvention
        # Priority: Snowflake (hardest to block via WebRTC) > obfs4 > direct
        if use_bridges:
            obfs4_proxy = os.path.join(pt_dir, "obfs4proxy.exe" if os.name == "nt" else "obfs4proxy")
            snowflake_client = os.path.join(pt_dir, "snowflake-client.exe" if os.name == "nt" else "snowflake-client")
            
            has_obfs4 = os.path.exists(obfs4_proxy)
            has_snowflake = os.path.exists(snowflake_client)
            
            if has_snowflake or has_obfs4:
                config.append("UseBridges 1")
                
                from src.services.bridge_fetcher import BridgeFetcher
                bridges_added = 0
                
                # Register Snowflake transport and add bridges (PRIMARY - harder to block)
                if has_snowflake:
                    logger.info(f"[TorService] Registering Snowflake transport: {snowflake_client}")
                    # Use absolute path and escape backslashes for torrc if needed, but Windows usually handles forward slashes or raw paths
                    # For torrc, paths with spaces need quotes
                    config.append(f'ClientTransportPlugin snowflake exec "{snowflake_client}"')
                    
                    snowflake_bridges = BridgeFetcher.get_bridges("snowflake")
                    logger.info(f"[TorService] Adding {len(snowflake_bridges)} Snowflake bridges (PRIMARY)")
                    for bridge in snowflake_bridges:
                        config.append(f"Bridge {bridge}")
                        bridges_added += 1
                
                # Register obfs4 transport and add bridges (FALLBACK)
                if has_obfs4:
                    logger.info(f"[TorService] Registering obfs4 transport: {obfs4_proxy}")
                    config.append(f'ClientTransportPlugin obfs4 exec "{obfs4_proxy}"')
                    
                    obfs4_bridges = BridgeFetcher.get_bridges("obfs4")
                    logger.info(f"[TorService] Adding {len(obfs4_bridges)} obfs4 bridges (FALLBACK)")
                    for bridge in obfs4_bridges:
                        config.append(f"Bridge {bridge}")
                        bridges_added += 1
                
                logger.info(f"[TorService] Total bridges configured: {bridges_added}")
            else:
                logger.warning(f"[TorService] No pluggable transports found, connecting directly")
                logger.warning(f"[TorService] PT Dir checked: {pt_dir}")
                logger.warning(f"[TorService] Files checked: {obfs4_proxy}, {snowflake_client}")

        # Write config file
        torrc_path = os.path.join(TOR_DATA_DIR, "torrc")
        with open(torrc_path, "w") as f:
            f.write("\n".join(config))
        
        logger.info(f"[TorService] Generated torrc configuration:")
        logger.info("-" * 40)
        logger.info("\n".join(config))
        logger.info("-" * 40)

        # Build command to use the config file
        cmd = [
            TOR_EXECUTABLE,
            "-f", torrc_path,
        ]

        logger.info(f"[TorService] Command: {' '.join(cmd)}")

        try:
            # Use subprocess.Popen directly with proper flags for Windows
            from src.utils.platform_utils import PlatformUtils
            
            log_handle = open(TOR_LOG_FILE, "w", encoding="utf-8")
            
            self._process = subprocess.Popen(
                cmd,
                stdout=log_handle,
                stderr=log_handle,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                startupinfo=PlatformUtils.get_startupinfo(),
            )

            if self._process:
                self._pid = self._process.pid
                logger.info(f"[TorService] Started with PID {self._pid}")
                
                with open(TOR_PID_FILE, "w") as f:
                    f.write(str(self._pid))

                # Allow some time for bootstrapping
                time.sleep(PROCESS_START_DELAY)
                
                # Check if process is still running
                if self._process.poll() is not None:
                    logger.error(f"[TorService] Process exited immediately with code {self._process.returncode}")
                    return None
                    
                return self._pid
            else:
                logger.error("[TorService] Failed to start process")
                return None
        except Exception as e:
            logger.error(f"[TorService] Failed to start Tor: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def stop(self) -> bool:
        """Stop Tor process."""
        pid_to_kill = self._pid
        if not pid_to_kill and os.path.exists(TOR_PID_FILE):
            try:
                with open(TOR_PID_FILE, "r") as f:
                    pid_to_kill = int(f.read().strip())
            except Exception:
                pass

        if not pid_to_kill:
            return True

        success = ProcessUtils.kill_process(pid_to_kill, force=True)
        if success:
            logger.info("[TorService] Stopped")
            self._pid = None
            self._process = None
            if os.path.exists(TOR_PID_FILE):
                try:
                    os.remove(TOR_PID_FILE)
                except Exception:
                    pass
        return success

    def is_running(self) -> bool:
        """Check if Tor is running."""
        if self._pid and ProcessUtils.is_running(self._pid):
            return True
        return False

    @property
    def pid(self) -> Optional[int]:
        """Get Tor process ID."""
        return self._pid

    @staticmethod
    def get_bootstrap_progress() -> tuple[int, str]:
        """
        Parse Tor log file for bootstrap progress.
        
        Returns:
            (percentage, status_message) tuple, e.g., (25, "Loading relay descriptors")
        """
        import re
        
        if not os.path.exists(TOR_LOG_FILE):
            return 0, "Starting..."
        
        try:
            with open(TOR_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            
            # Search from end for most recent bootstrap line
            # Format: [notice] Bootstrapped 25% (loading_descriptors): Loading relay descriptors
            pattern = r"Bootstrapped (\d+)% \([^)]+\): (.+)"
            
            for line in reversed(lines):
                match = re.search(pattern, line)
                if match:
                    percentage = int(match.group(1))
                    message = match.group(2).strip()
                    return percentage, message
            
            return 0, "Starting..."
        except Exception:
            return 0, "Starting..."
