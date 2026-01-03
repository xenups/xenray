"""Tor Installer Service."""
import os
import shutil
import tarfile
import tempfile
from typing import Callable, Optional

import requests
from loguru import logger

from src.core.constants import BIN_DIR, TOR_EXECUTABLE
from src.utils.platform_utils import PlatformUtils

# Constants
DOWNLOAD_TIMEOUT = 60.0  # seconds
MIN_FILE_SIZE = 1024  # bytes
# Using a fixed stable version for now, ideally this would be dynamic
TOR_VERSION = "15.0.3"
TOR_BUNDLE_URL = f"https://dist.torproject.org/torbrowser/{TOR_VERSION}/tor-expert-bundle-windows-x86_64-{TOR_VERSION}.tar.gz"

class TorInstallerService:
    """Manages Tor installation."""

    @staticmethod
    def is_installed() -> bool:
        """Check if Tor is installed."""
        return os.path.exists(TOR_EXECUTABLE)

    @staticmethod
    def install(
        progress_callback: Optional[Callable[[str], None]] = None,
        stop_service_callback: Optional[Callable[[], None]] = None,
    ) -> bool:
        """Install Tor."""
        try:
            os.makedirs(BIN_DIR, exist_ok=True)

            if progress_callback:
                progress_callback("Downloading Tor Expert Bundle...")
            
            tar_path = TorInstallerService._download_bundle(progress_callback)
            if not tar_path:
                return False

            if stop_service_callback:
                try:
                    stop_service_callback()
                except Exception as e:
                    logger.warning(f"Error stopping service: {e}")

            if progress_callback:
                progress_callback("Installing Tor binary...")
            
            if not TorInstallerService._extract_bundle(tar_path):
                return False

            if progress_callback:
                progress_callback("Tor installation complete!")
            return True
        except Exception as e:
            logger.error(f"Tor install failed: {e}")
            if progress_callback:
                progress_callback(f"Installation failed: {e}")
            return False

    @staticmethod
    def _download_bundle(progress_callback: Optional[Callable[[str], None]] = None) -> Optional[str]:
        """Download Tor bundle to temp location."""
        try:
            # For now, we only support windows x86_64 as per user context
            url = TOR_BUNDLE_URL
            tar_path = os.path.join(tempfile.gettempdir(), "tor_bundle.tar.gz")
            
            response = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
            response.raise_for_status()

            with open(tar_path, "wb") as f:
                shutil.copyfileobj(response.raw, f)

            if not os.path.exists(tar_path) or os.path.getsize(tar_path) < MIN_FILE_SIZE:
                logger.error("Downloaded file validation failed")
                return None

            return tar_path
        except Exception as e:
            logger.error(f"Failed to download Tor bundle: {e}")
            return None

    @staticmethod
    def _extract_bundle(tar_path: str) -> bool:
        """Extract Tor binary from tar.gz."""
        try:
            with tarfile.open(tar_path, "r:gz") as tar:
                # The bundle has a nested structure: tor/tor.exe, etc.
                # We want the contents of the 'tor' folder or specific files.
                # Let's extract everything to a temp dir first to see structure or just extract all to BIN_DIR
                tar.extractall(BIN_DIR)

            # Clean up temp file
            try:
                os.remove(tar_path)
            except OSError:
                pass

            # The expert bundle on Windows usually extracts as a 'tor' directory inside BIN_DIR
            # We might need to move tor.exe to BIN_DIR directly if TOR_EXECUTABLE expects it there.
            expected_tor_exe = os.path.join(BIN_DIR, "tor", "tor.exe")
            if os.path.exists(expected_tor_exe):
                # Move all files from BIN_DIR/tor to BIN_DIR
                tor_inner_dir = os.path.join(BIN_DIR, "tor")
                
                # Setup TMPDIR transport location
                from src.core.constants import TMPDIR
                tor_pt_dir = os.path.join(TMPDIR, "tor_pt")
                if os.path.exists(tor_pt_dir):
                    shutil.rmtree(tor_pt_dir)
                os.makedirs(tor_pt_dir, exist_ok=True)
                
                for item in os.listdir(tor_inner_dir):
                    s = os.path.join(tor_inner_dir, item)
                    
                    # Move pluggable_transports to TMPDIR to avoid permission issues
                    if item == "pluggable_transports":
                        logger.info(f"[TorInstaller] Moving pluggable transports to {tor_pt_dir}")
                        # Move contents of pluggable_transports to tor_pt_dir
                        for pt_item in os.listdir(s):
                            shutil.move(os.path.join(s, pt_item), os.path.join(tor_pt_dir, pt_item))
                        # Remove the original folder
                        shutil.rmtree(s)
                        continue
                    
                    # For other files/folders, move to BIN_DIR as usual
                    d = os.path.join(BIN_DIR, item)
                    
                    if os.path.exists(d):
                        if os.path.isdir(d):
                            shutil.rmtree(d)
                        else:
                            os.remove(d)
                    shutil.move(s, d)
                os.rmdir(tor_inner_dir)

            return True
        except Exception as e:
            logger.error(f"Failed to extract Tor bundle: {e}")
            return False
