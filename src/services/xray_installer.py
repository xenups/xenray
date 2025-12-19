"""Xray Installer Service."""
import os
import shutil
import subprocess
import tempfile
import zipfile
from typing import Callable, Optional

import requests
from loguru import logger

from src.core.constants import BIN_DIR, XRAY_EXECUTABLE
from src.utils.platform_utils import PlatformUtils

# Constants
DOWNLOAD_TIMEOUT = 30.0  # seconds
MIN_FILE_SIZE = 1024  # bytes - minimum expected file size


class XrayInstallerService:
    """Manages Xray installation."""

    @staticmethod
    def is_installed() -> bool:
        """Check if Xray is installed."""
        return os.path.exists(XRAY_EXECUTABLE)

    @staticmethod
    def install(
        progress_callback: Optional[Callable[[str], None]] = None,
        stop_service_callback: Optional[Callable[[], None]] = None,
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
            # os.makedirs(ASSETS_DIR, exist_ok=True)
            # Assets dir might still be needed for other things, but ensuring it here isn't strictly necessary
            # for only Xray bin if we aren't downloading geo files.
            # But keeping it safe doesn't hurt, or we can just remove it if empty.
            # Reviewing: Xray binary goes to BIN_DIR. ASSETS_DIR was for geo files.
            # If we don't download geo files, we might not need to create ASSETS_DIR here.
            # However, to be safe and clean, I will just remove the line creating ASSETS_DIR if it's not used.

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

            if progress_callback:
                progress_callback("Installation complete!")
            return True
        except Exception as e:
            logger.error(f"Xray install failed: {e}")
            if progress_callback:
                progress_callback(f"Installation failed: {e}")
            return False

    @staticmethod
    def _download_core(
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Optional[str]:
        """
        Download Xray core to temp location.

        Returns:
            Path to zip file, or None if download failed
        """
        try:
            # Determine architecture
            arch = PlatformUtils.get_architecture()
            if arch == "x86_64":
                arch_str = "64"
            elif arch == "arm64":
                arch_str = "arm64-v8a"
            else:
                arch_str = "32"

            # Determine OS name
            platform = PlatformUtils.get_platform()
            if platform == "windows":
                os_name = "windows"
            elif platform == "macos":
                os_name = "macos"
            else:
                os_name = "linux"

            filename = f"Xray-{os_name}-{arch_str}.zip"
            url = (
                f"https://github.com/XTLS/Xray-core/releases/latest/download/{filename}"
            )

            if progress_callback:
                progress_callback(f"Downloading {filename}...")

            # Download to temp directory first
            zip_path = os.path.join(tempfile.gettempdir(), "xray_update.zip")
            response = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
            response.raise_for_status()

            # Validate file size
            total_size = int(response.headers.get("content-length", 0))
            if total_size < MIN_FILE_SIZE:
                logger.error(f"Downloaded file too small: {total_size} bytes")
                return None

            with open(zip_path, "wb") as f:
                shutil.copyfileobj(response.raw, f)

            # Verify file exists and has reasonable size
            if (
                not os.path.exists(zip_path)
                or os.path.getsize(zip_path) < MIN_FILE_SIZE
            ):
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

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
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
    def get_local_version() -> Optional[str]:
        """
        Get installed Xray version.
        Returns version string (e.g., "1.8.4") or None.
        """
        if not os.path.exists(XRAY_EXECUTABLE):
            return None

        try:
            # Run xray -version
            # Output format: Xray 1.8.4 (Xray, Penetrator through the void.) ...
            result = subprocess.run(
                [XRAY_EXECUTABLE, "-version"],
                capture_output=True,
                text=True,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )

            if result.returncode == 0:
                first_line = result.stdout.split("\n")[0]
                parts = first_line.split()
                if len(parts) >= 2:
                    return parts[1]  # "1.8.4"
            return None
        except Exception as e:
            logger.warning(f"Failed to check Xray version: {e}")
            return None

    @staticmethod
    def check_for_updates() -> tuple[bool, Optional[str], Optional[str]]:
        """
        Check for updates via GitHub API.
        Returns: (update_available, current_version, latest_version)
        """
        current_version = XrayInstallerService.get_local_version()
        try:
            url = "https://api.github.com/repos/XTLS/Xray-core/releases/latest"
            response = requests.get(url, timeout=10)  # Short timeout for API check
            response.raise_for_status()

            data = response.json()
            tag_name = data.get("tag_name", "")  # e.g., "v1.8.4" or "1.8.4"

            # Normalize version strings (remove 'v' prefix from both versions)
            latest_version = tag_name.lstrip("v")
            current_version_normalized = current_version.lstrip("v") if current_version else None

            # Debug logging
            logger.info(f"Version check - Current (normalized): {current_version_normalized}")
            logger.info(f"Version check - Latest (normalized): {latest_version}")

            if not current_version_normalized:
                logger.info("No current version found, update available")
                return True, None, latest_version

            if current_version_normalized != latest_version:
                logger.info(f"Update available: {current_version_normalized} -> {latest_version}")
                return True, current_version_normalized, latest_version

            logger.info("Already up to date")
            return False, current_version_normalized, latest_version

        except Exception as e:
            logger.error(f"Failed to check for updates: {e}")
            return False, current_version, None
