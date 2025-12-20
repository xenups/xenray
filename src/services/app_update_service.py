"""App Update Service.

This service handles checking for and installing application updates from GitHub releases.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional, Tuple

import requests
from loguru import logger

from src.core.constants import APP_VERSION, GITHUB_REPO, UPDATE_DOWNLOAD_TIMEOUT, UPDATE_MIN_FILE_SIZE
from src.utils.platform_utils import PlatformUtils

# API URL constructed from configurable repo
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


class AppUpdateService:
    """Manages application updates from GitHub releases."""

    @staticmethod
    def get_current_version() -> str:
        """
        Get the current app version.

        Returns:
            Version string (e.g., "0.1.5-alpha")
        """
        return APP_VERSION

    @staticmethod
    def parse_version(version_str: str) -> str:
        """
        Normalize version string by removing 'v' prefix.

        Args:
            version_str: Version string (e.g., "v1.0.0" or "1.0.0")

        Returns:
            Normalized version string without 'v' prefix
        """
        return version_str.lstrip("v")

    @staticmethod
    def compare_versions(current: str, latest: str) -> bool:
        """
        Compare two version strings.

        Args:
            current: Current version
            latest: Latest version

        Returns:
            True if latest is newer than current
        """
        # Normalize versions (remove 'v' prefix)
        current_normalized = AppUpdateService.parse_version(current)
        latest_normalized = AppUpdateService.parse_version(latest)

        try:
            from packaging import version

            return version.parse(latest_normalized) > version.parse(current_normalized)
        except Exception:
            # Fallback: simple string comparison (only if versions are different)
            # This is not ideal but prevents false positives
            logger.warning(f"Failed to compare versions properly: {current} vs {latest}")
            return current_normalized != latest_normalized

    @staticmethod
    def check_for_updates() -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Check for updates via GitHub API.

        Returns:
            Tuple of (update_available, current_version, latest_version, download_url)
        """
        current_version = AppUpdateService.get_current_version()

        try:
            logger.info(f"Checking for updates... Current version: {current_version}")

            # Query GitHub API
            response = requests.get(GITHUB_API_URL, timeout=10)
            response.raise_for_status()

            data = response.json()
            tag_name = data.get("tag_name", "")
            latest_version = AppUpdateService.parse_version(tag_name)

            # Find the appropriate asset for this platform
            download_url = AppUpdateService._find_asset_url(data.get("assets", []))

            if not download_url:
                logger.warning("No compatible asset found in release")
                return False, current_version, latest_version, None

            # Check if update is available
            if AppUpdateService.compare_versions(current_version, latest_version):
                logger.info(f"Update available: {current_version} → {latest_version}")
                return True, current_version, latest_version, download_url

            logger.info("App is up to date")
            return False, current_version, latest_version, download_url

        except Exception as e:
            logger.error(f"Failed to check for updates: {e}")
            return False, current_version, None, None

    @staticmethod
    def _find_asset_url(assets: list) -> Optional[str]:
        """
        Find the download URL for the appropriate platform asset.

        Args:
            assets: List of asset objects from GitHub API

        Returns:
            Download URL or None
        """
        platform = PlatformUtils.get_platform()
        arch = PlatformUtils.get_architecture()

        # Determine asset name pattern
        if platform == "windows":
            if arch == "x86_64":
                pattern = "windows-x64.zip"
            else:
                pattern = "windows-x86.zip"
        elif platform == "linux":
            pattern = "linux.AppImage"  # Future support
        elif platform == "macos":
            pattern = "macos.dmg"  # Future support
        else:
            return None

        # Find matching asset
        for asset in assets:
            name = asset.get("name", "")
            if pattern in name.lower():
                return asset.get("browser_download_url")

        return None

    @staticmethod
    def download_update(url: str, progress_callback: Optional[Callable[[int], None]] = None) -> Optional[str]:
        """
        Download update ZIP file.

        Args:
            url: Download URL
            progress_callback: Function to report progress (0-100)

        Returns:
            Path to downloaded file, or None on failure
        """
        try:
            logger.info(f"Downloading update from: {url}")

            # Download to temp directory
            zip_path = os.path.join(tempfile.gettempdir(), "xenray_update.zip")

            # Stream download with progress
            response = requests.get(url, stream=True, timeout=UPDATE_DOWNLOAD_TIMEOUT)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))

            if total_size < UPDATE_MIN_FILE_SIZE:
                logger.error(f"Downloaded file too small: {total_size} bytes")
                return None

            downloaded_size = 0
            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        if progress_callback and total_size > 0:
                            progress = int((downloaded_size / total_size) * 100)
                            progress_callback(progress)

            # Verify download
            if not os.path.exists(zip_path) or os.path.getsize(zip_path) < UPDATE_MIN_FILE_SIZE:
                logger.error("Downloaded file validation failed")
                return None

            logger.info(f"Download complete: {zip_path}")
            return zip_path

        except Exception as e:
            logger.error(f"Failed to download update: {e}")
            return None

    @staticmethod
    def create_updater_script(zip_path: str, app_dir: str) -> Optional[str]:
        """
        Create PowerShell updater script.

        The script will:
        1. Wait for main process to exit
        2. Extract ZIP to app directory
        3. Restart the app
        4. Delete itself

        Args:
            zip_path: Path to downloaded ZIP
            app_dir: Application directory

        Returns:
            Path to updater script copy, or None on failure
        """
        try:
            # Get current process ID
            pid = os.getpid()

            # Log mode and paths for debugging
            is_frozen = getattr(sys, "frozen", False)
            logger.info(f"[AppUpdate] Running in {'EXE' if is_frozen else 'DEV'} mode")
            logger.info(f"[AppUpdate] sys.executable: {sys.executable}")
            logger.info(f"[AppUpdate] app_dir: {app_dir}")
            logger.info(f"[AppUpdate] zip_path: {zip_path}")
            logger.info(f"[AppUpdate] PID: {pid}")

            # Determine executable path
            if is_frozen:
                exe_path = sys.executable
                logger.info(f"[AppUpdate] EXE path (frozen): {exe_path}")
            else:
                # Development mode - use poetry run
                exe_path = os.path.join(app_dir, "XenRay.exe")
                logger.info(f"[AppUpdate] EXE path (dev): {exe_path}")

            # Find the updater script template
            if is_frozen:
                # Running as exe - script should be in scripts/ next to exe
                script_template = os.path.join(os.path.dirname(sys.executable), "scripts", "xenray_updater.ps1")
                logger.info(f"[AppUpdate] Looking for script in EXE dir: {script_template}")
            else:
                # Running from source
                script_template = os.path.join(Path(__file__).parent.parent.parent, "scripts", "xenray_updater.ps1")
                logger.info(f"[AppUpdate] Looking for script in source dir: {script_template}")

            if not os.path.exists(script_template):
                logger.error(f"[AppUpdate] Updater script NOT FOUND: {script_template}")
                # List what IS in the scripts directory for debugging
                scripts_dir = os.path.dirname(script_template)
                if os.path.exists(scripts_dir):
                    files = os.listdir(scripts_dir)
                    logger.error(f"[AppUpdate] Files in {scripts_dir}: {files}")
                else:
                    logger.error(f"[AppUpdate] Scripts directory does not exist: {scripts_dir}")
                return None

            logger.info(f"[AppUpdate] Script template found: {script_template}")

            # Create a copy in temp directory with parameters file
            script_copy = os.path.join(tempfile.gettempdir(), "xenray_updater_run.ps1")
            shutil.copy(script_template, script_copy)
            logger.info(f"[AppUpdate] Copied script to: {script_copy}")

            # Create wrapper script that calls the main script with parameters
            wrapper_path = os.path.join(tempfile.gettempdir(), "xenray_update_launcher.ps1")
            wrapper_content = f"""
# XenRay Update Launcher
& "{script_copy}" -ProcessID {pid} -ZipPath "{zip_path}" -AppDir "{app_dir}" -ExePath "{exe_path}"
"""

            with open(wrapper_path, "w", encoding="utf-8") as f:
                f.write(wrapper_content)

            logger.info(f"[AppUpdate] Created wrapper script: {wrapper_path}")
            logger.info(f"[AppUpdate] Wrapper content:\n{wrapper_content}")
            return wrapper_path

        except Exception as e:
            logger.error(f"Failed to create updater script: {e}")
            return None

    @staticmethod
    def apply_update(zip_path: str) -> bool:
        """
        Apply the update by launching updater script.

        Args:
            zip_path: Path to downloaded ZIP

        Returns:
            True if updater was launched successfully
        """
        try:
            # Get app directory
            if getattr(sys, "frozen", False):
                app_dir = os.path.dirname(sys.executable)
            else:
                app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

            logger.info(f"Applying update to: {app_dir}")

            # Create updater script
            script_path = AppUpdateService.create_updater_script(zip_path, app_dir)
            if not script_path:
                return False

            # Launch updater script as detached process
            # Use START command for reliable detached launch on Windows
            cmd = f'start "" powershell.exe -ExecutionPolicy Bypass -File "{script_path}"'
            subprocess.Popen(
                cmd,
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            logger.info("Updater script launched successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to apply update: {e}")
            return False
