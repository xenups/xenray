"""Xray Installer Service."""
import os
import platform
import shutil
import sys
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
    def install(progress_callback=None) -> bool:
        """Install Xray and geo files."""
        try:
            os.makedirs(BIN_DIR, exist_ok=True)
            os.makedirs(ASSETS_DIR, exist_ok=True)
            
            # 1. Install Xray Core
            if progress_callback: progress_callback("Downloading Xray Core...")
            XrayInstallerService._install_core()
            
            # 2. Install Geo Files
            if progress_callback: progress_callback("Downloading Geo Files...")
            XrayInstallerService._install_geo_files()
            
            return True
        except Exception as e:
            print(f"Xray install failed: {e}")
            return False

    @staticmethod
    def _install_core():
        """Download and extract Xray core."""
        # Determine architecture
        arch = platform.machine().lower()
        if arch == "amd64" or arch == "x86_64":
            arch_str = "64"
        elif "arm" in arch:
            arch_str = "arm64-v8a" # Simplified
        else:
            arch_str = "32"
            
        os_name = "windows" if os.name == 'nt' else "linux"
        filename = f"Xray-{os_name}-{arch_str}.zip"
        url = f"https://github.com/XTLS/Xray-core/releases/latest/download/{filename}"
        
        # Download
        zip_path = os.path.join(BIN_DIR, "xray.zip")
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(zip_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)
                
        # Extract
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
