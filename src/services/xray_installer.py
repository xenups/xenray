"""Xray Installer Service."""
import os
import platform
import shutil
import tempfile
import zipfile

import requests

from src.core.constants import ASSETS_DIR, BIN_DIR, XRAY_EXECUTABLE


class XrayInstallerService:
    """Manages Xray installation."""
    
    @staticmethod
    def is_installed() -> bool:
        """Check if Xray is installed."""
        return os.path.exists(XRAY_EXECUTABLE) and \
               os.path.exists(os.path.join(ASSETS_DIR, "geosite.dat")) and \
               os.path.exists(os.path.join(ASSETS_DIR, "geoip.dat"))

    @staticmethod
    def install(progress_callback=None, stop_service_callback=None) -> bool:
        """
        Install Xray and geo files.
        
        Args:
            progress_callback: Function to report progress
            stop_service_callback: Function to stop xray service before file replacement
        """
        try:
            os.makedirs(BIN_DIR, exist_ok=True)
            os.makedirs(ASSETS_DIR, exist_ok=True)
            
            # 1. Download Xray Core to temp location first
            if progress_callback: progress_callback("Downloading Xray Core...")
            zip_path = XrayInstallerService._download_core()
            
            # 2. STOP xray service AFTER download, BEFORE extraction
            if progress_callback: progress_callback("Stopping Xray service...")
            if stop_service_callback:
                stop_service_callback()
            
            # 3. Extract (replace files)
            if progress_callback: progress_callback("Installing Xray Core...")
            XrayInstallerService._extract_core(zip_path)
            
            # 4. Install Geo Files
            if progress_callback: progress_callback("Downloading Geo Files...")
            XrayInstallerService._install_geo_files()
            
            return True
        except Exception as e:
            print(f"Xray install failed: {e}")
            return False

    @staticmethod
    def _download_core() -> str:
        """Download Xray core to temp location. Returns path to zip file."""
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
        
        # Download to temp directory first
        zip_path = os.path.join(tempfile.gettempdir(), "xray_update.zip")
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(zip_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)
        
        return zip_path
    
    @staticmethod
    def _extract_core(zip_path: str):
        """Extract Xray core from zip file."""
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(BIN_DIR)
        os.remove(zip_path)

    @staticmethod
    def _install_geo_files():
        """Download geoip and geosite."""
        base_url = "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download"
        
        for file in ["geoip.dat", "geosite.dat"]:
            url = f"{base_url}/{file}"
            path = os.path.join(ASSETS_DIR, file)
            
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
