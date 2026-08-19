"""Core download responsibility — HTTP streaming with retry and timeouts.

Owns: Xray-core zip download and generic streamed file download (used by the
wintun.dll bootstrap). No extraction, no version logic.
"""

from __future__ import annotations

import os
import tempfile
from typing import Callable, Optional

import requests
from loguru import logger

from src.platform.constants import (
    XRAY_CORE_ASSET_EXTENSION,
    XRAY_CORE_DOWNLOAD_BASE_URL,
    XRAY_CORE_ZIP_FILENAME,
    XRAY_DOWNLOAD_CHUNK_SIZE,
    XRAY_DOWNLOAD_CONNECT_TIMEOUT,
    XRAY_DOWNLOAD_MAX_RETRIES,
    XRAY_DOWNLOAD_MIN_FILE_SIZE,
    XRAY_DOWNLOAD_READ_TIMEOUT,
)
from src.utils.platform_utils import PlatformUtils


class FileDownloader:
    """Stream downloads a file from a URL with retries and explicit timeouts."""

    def __init__(
        self,
        connect_timeout: float = XRAY_DOWNLOAD_CONNECT_TIMEOUT,
        read_timeout: float = XRAY_DOWNLOAD_READ_TIMEOUT,
        chunk_size: int = XRAY_DOWNLOAD_CHUNK_SIZE,
        min_file_size: int = XRAY_DOWNLOAD_MIN_FILE_SIZE,
        max_retries: int = XRAY_DOWNLOAD_MAX_RETRIES,
    ):
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._chunk_size = chunk_size
        self._min_file_size = min_file_size
        self._max_retries = max_retries

    def download(
        self,
        url: str,
        dest_path: str,
        progress_callback: Optional[Callable[[str], None]] = None,
        label: Optional[str] = None,
    ) -> Optional[str]:
        """Download *url* to *dest_path*; returns path on success, else None.

        *label* (e.g. the archive filename) is used in progress/log messages so
        the UI reports what is actually being fetched.
        """
        name = label or os.path.basename(dest_path)
        for attempt in range(1, self._max_retries + 1):
            try:
                if progress_callback:
                    progress_callback(f"Downloading {name} (attempt {attempt}/{self._max_retries})...")

                logger.info(f"Downloading {url} (attempt {attempt})")
                response = requests.get(
                    url,
                    stream=True,
                    timeout=(self._connect_timeout, self._read_timeout),
                )
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", 0))
                if total_size and total_size < self._min_file_size:
                    logger.error(f"Content-Length too small: {total_size} bytes")
                    continue

                downloaded = 0
                with open(dest_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=self._chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total_size:
                                pct = int(downloaded * 100 / total_size)
                                progress_callback(f"Downloading... {pct}%")

                if not os.path.exists(dest_path) or os.path.getsize(dest_path) < self._min_file_size:
                    logger.error(f"Downloaded file too small or missing (attempt {attempt})")
                    continue

                logger.info(f"Download complete: {os.path.getsize(dest_path)} bytes")
                return dest_path

            except requests.exceptions.Timeout:
                logger.warning(f"Download timed out (attempt {attempt}/{self._max_retries})")
                if progress_callback:
                    progress_callback(f"Timeout, retrying... ({attempt}/{self._max_retries})")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error (attempt {attempt}): {e}")
                if progress_callback:
                    progress_callback(f"Connection error, retrying... ({attempt}/{self._max_retries})")
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
                if os.path.exists(dest_path):
                    os.remove(dest_path)
            except OSError:
                pass

        logger.error(f"All {self._max_retries} download attempts failed")
        if progress_callback:
            progress_callback("Download failed after all retries.")
        return None

    @staticmethod
    def temp_dest(filename: str) -> str:
        """Absolute temp path for a downloaded archive."""
        return os.path.join(tempfile.gettempdir(), filename)

    def download_xray_core(
        self,
        progress_callback: Optional[Callable[[str], None]] = None,
        target_version: Optional[str] = None,
    ) -> Optional[str]:
        """Download the Xray-core release zip for the current platform.

        Returns the temp zip path, or None if every attempt failed.
        """
        from src.core.constants import XRAY_VERSION

        arch = PlatformUtils.get_architecture()
        if arch == "x86_64":
            arch_str = "64"
        elif arch == "arm64":
            arch_str = "arm64-v8a"
        else:
            arch_str = "32"

        platform = PlatformUtils.get_platform()
        if platform == "windows":
            os_name = "windows"
        elif platform == "macos":
            os_name = "macos"
        else:
            os_name = "linux"

        filename = f"Xray-{os_name}-{arch_str}{XRAY_CORE_ASSET_EXTENSION}"
        version = (target_version or XRAY_VERSION).lstrip("v")
        url = f"{XRAY_CORE_DOWNLOAD_BASE_URL}/v{version}/{filename}"

        return self.download(
            url,
            self.temp_dest(XRAY_CORE_ZIP_FILENAME),
            progress_callback=progress_callback,
            label=filename,
        )
