"""Xray Installer Service."""
import os
import platform
import shutil
import tempfile
import zipfile
from typing import Optional, Callable

import requests
from loguru import logger

from src.core.constants import ASSETS_DIR, BIN_DIR, XRAY_EXECUTABLE

# Constants
DOWNLOAD_TIMEOUT = 30.0  # seconds
MIN_FILE_SIZE = 1024  # bytes - minimum expected file size


class XrayInstallerService:
    """Manages Xray installation."""
    
    @staticmethod
    def is_installed() -> bool:
        """Check if Xray is installed."""
        return os.path.exists(XRAY_EXECUTABLE) and \
               os.path.exists(os.path.join(ASSETS_DIR, "geosite.dat")) and \
               os.path.exists(os.path.join(ASSETS_DIR, "geoip.dat"))

    @staticmethod
    def install(
        progress_callback: Optional[Callable[[str], None]] = None,
        stop_service_callback: Optional[Callable[[], None]] = None
    ) -> bool:
        """
        Install Xray and geo files.
        
        Args:
            progress_callback: Function to report progress
            stop_service_callback: Function to stop xray service before file replacement
            
        Returns:
            True if successful, False otherwise
        """
        try:
            os.makedirs(BIN_DIR, exist_ok=True)
            os.makedirs(ASSETS_DIR, exist_ok=True)
            
            # 1. Download Xray Core to temp location first
            if progress_callback:
                progress_callback("Downloading Xray Core...")
            zip_path = XrayInstallerService._download_core(progress_callback)
            if not zip_path:
                return False
            
            # 2. STOP xray service AFTER download, BEFORE extraction
            if progress_callback:
                progress_callback("Stopping Xray service...")
            if stop_service_callback:
                try:
                    stop_service_callback()
                except Exception as e:
                    logger.warning(f"Error stopping service: {e}")
            
            # 3. Extract (replace files)
            if progress_callback:
                progress_callback("Installing Xray Core...")
            if not XrayInstallerService._extract_core(zip_path):
                return False
            
            # 4. Install Geo Files
            if progress_callback:
                progress_callback("Downloading Geo Files...")
            if not XrayInstallerService._install_geo_files(progress_callback):
                return False
            
            if progress_callback:
                progress_callback("Installation complete!")
            return True
        except Exception as e:
            logger.error(f"Xray install failed: {e}")
            if progress_callback:
                progress_callback(f"Installation failed: {e}")
            return False

    @staticmethod
    def _download_core(progress_callback: Optional[Callable[[str], None]] = None) -> Optional[str]:
        """
        Download Xray core to temp location.
        
        Returns:
            Path to zip file, or None if download failed
        """
        try:
            # Determine architecture
            arch = platform.machine().lower()
            if arch == "amd64" or arch == "x86_64":
                arch_str = "64"
            elif "arm" in arch:
                arch_str = "arm64-v8a"
            else:
                arch_str = "32"
                
            os_name = "windows" if os.name == 'nt' else "linux"
            filename = f"Xray-{os_name}-{arch_str}.zip"
            url = f"https://github.com/XTLS/Xray-core/releases/latest/download/{filename}"
            
            if progress_callback:
                progress_callback(f"Downloading {filename}...")
            
            # Download to temp directory first
            zip_path = os.path.join(tempfile.gettempdir(), "xray_update.zip")
            response = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
            response.raise_for_status()
            
            # Validate file size
            total_size = int(response.headers.get('content-length', 0))
            if total_size < MIN_FILE_SIZE:
                logger.error(f"Downloaded file too small: {total_size} bytes")
                return None
            
            with open(zip_path, 'wb') as f:
                shutil.copyfileobj(response.raw, f)
            
            # Verify file exists and has reasonable size
            if not os.path.exists(zip_path) or os.path.getsize(zip_path) < MIN_FILE_SIZE:
                logger.error("Downloaded file validation failed")
                return None
            
            return zip_path
        except (requests.RequestException, OSError, IOError) as e:
            logger.error(f"Failed to download Xray core: {e}")
            return None
    
    @staticmethod
    def _extract_core(zip_path: str) -> bool:
        """
        Extract Xray core from zip file.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if not os.path.exists(zip_path):
                logger.error(f"Zip file not found: {zip_path}")
                return False
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(BIN_DIR)
            
            # Clean up temp file
            try:
                os.remove(zip_path)
            except OSError as e:
                logger.warning(f"Failed to remove temp file: {e}")
            
            return True
        except (zipfile.BadZipFile, OSError, IOError) as e:
            logger.error(f"Failed to extract Xray core: {e}")
            return False

    @staticmethod
    def _install_geo_files(progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Download geoip and geosite files.
        
        Returns:
            True if successful, False otherwise
        """
        base_url = "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download"
        
        for file in ["geoip.dat", "geosite.dat"]:
            url = f"{base_url}/{file}"
            path = os.path.join(ASSETS_DIR, file)
            
            if progress_callback:
                progress_callback(f"Downloading {file}...")
            
            try:
                response = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
                response.raise_for_status()
                
                # Use atomic write
                temp_path = path + ".tmp"
                with open(temp_path, 'wb') as f:
                    shutil.copyfileobj(response.raw, f)
                
                # Validate file size
                if os.path.getsize(temp_path) < MIN_FILE_SIZE:
                    logger.error(f"Downloaded {file} too small")
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
                    return False
                
                # Atomic rename
                if os.name == "nt":
                    os.replace(temp_path, path)
                else:
                    os.rename(temp_path, path)
                    
            except (requests.RequestException, OSError, IOError) as e:
                logger.error(f"Failed to download {file}: {e}")
                return False
        
        return True
