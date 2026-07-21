"""Xray Installer Service."""
import os
import shutil
import subprocess
import tempfile
import zipfile
from typing import Callable, Optional

import requests
from loguru import logger

from src.core.constants import BIN_DIR, XRAY_EXECUTABLE, XRAY_VERSION
from src.utils.platform_utils import PlatformUtils

# Constants
CONNECT_TIMEOUT = 15.0       # seconds to establish connection
READ_TIMEOUT = 60.0          # seconds between data chunks (prevents infinite stall)
CHUNK_SIZE = 65536           # 64 KB read chunks for streaming download
MIN_FILE_SIZE = 1024         # bytes — minimum expected file size
MAX_RETRIES = 3              # number of download attempts before giving up


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
        target_version: Optional[str] = None,
    ) -> bool:
        """
        Install Xray and geo files.

        Args:
            progress_callback: Function to report progress
            stop_service_callback: Function to stop xray service before file replacement
            target_version: Specific version to download (e.g. "25.1.1").
                            Falls back to XRAY_VERSION constant if not provided.

        Returns:
            True if successful, False otherwise
        """
        try:
            os.makedirs(BIN_DIR, exist_ok=True)

            # 1. Download Xray Core to temp location first
            if progress_callback:
                progress_callback("Downloading Xray Core...")
            zip_path = XrayInstallerService._download_core(
                progress_callback=progress_callback,
                target_version=target_version,
            )
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
        progress_callback: Optional[Callable[[str], None]] = None,
        target_version: Optional[str] = None,
    ) -> Optional[str]:
        """
        Download Xray core to temp location with retry logic and proper timeouts.

        Returns:
            Path to zip file, or None if all attempts failed.
        """
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

        # Prefer the explicitly requested version, fall back to pinned constant
        version = (target_version or XRAY_VERSION).lstrip("v")
        url = f"https://github.com/XTLS/Xray-core/releases/download/v{version}/{filename}"

        zip_path = os.path.join(tempfile.gettempdir(), "xray_update.zip")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if progress_callback:
                    msg = f"Downloading {filename} (attempt {attempt}/{MAX_RETRIES})..."
                    progress_callback(msg)

                logger.info(f"Downloading Xray from: {url} (attempt {attempt})")

                # Use explicit (connect, read) timeout tuple to prevent infinite stall.
                # Without a read timeout, shutil.copyfileobj can hang forever on a
                # stalled server connection.
                response = requests.get(
                    url,
                    stream=True,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                )
                response.raise_for_status()

                # Validate content-length header when present
                total_size = int(response.headers.get("content-length", 0))
                if total_size and total_size < MIN_FILE_SIZE:
                    logger.error(f"Content-Length too small: {total_size} bytes")
                    continue

                # Stream download in chunks (avoids memory pressure & enables
                # progress reporting without a separate read-timeout risk)
                downloaded = 0
                with open(zip_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total_size:
                                pct = int(downloaded * 100 / total_size)
                                progress_callback(f"Downloading... {pct}%")

                # Verify downloaded file
                if not os.path.exists(zip_path) or os.path.getsize(zip_path) < MIN_FILE_SIZE:
                    logger.error(f"Downloaded file too small or missing (attempt {attempt})")
                    continue

                logger.info(f"Download complete: {os.path.getsize(zip_path)} bytes")
                return zip_path

            except requests.exceptions.Timeout:
                logger.warning(f"Download timed out (attempt {attempt}/{MAX_RETRIES})")
                if progress_callback:
                    progress_callback(f"Timeout, retrying... ({attempt}/{MAX_RETRIES})")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error (attempt {attempt}): {e}")
                if progress_callback:
                    progress_callback(f"Connection error, retrying... ({attempt}/{MAX_RETRIES})")
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error: {e}")
                if progress_callback:
                    progress_callback(f"HTTP error: {e.response.status_code}")
                # Don't retry on 4xx client errors
                if e.response is not None and e.response.status_code < 500:
                    return None
            except (OSError, IOError) as e:
                logger.error(f"File I/O error (attempt {attempt}): {e}")

            # Clean up partial file before retry
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
            except OSError:
                pass

        logger.error(f"All {MAX_RETRIES} download attempts failed")
        if progress_callback:
            progress_callback("Download failed after all retries.")
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
            result = subprocess.run(
                [XRAY_EXECUTABLE, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
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
            response = requests.get(url, timeout=(10, 15))
            response.raise_for_status()

            data = response.json()
            tag_name = data.get("tag_name", "")  # e.g., "v1.8.4" or "1.8.4"

            # Normalize version strings (remove 'v' prefix from both versions)
            latest_version = tag_name.lstrip("v")
            current_version_normalized = current_version.lstrip("v") if current_version else None

            logger.info(f"Version check — current: {current_version_normalized}, latest: {latest_version}")

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
