"""Windows TUN driver adapter — manages wintun.dll bootstrap and verification."""

from __future__ import annotations

import os
import tempfile
from typing import Callable, Optional

from loguru import logger

from src.core.constants import BIN_DIR, WINTUN_DLL, WINTUN_DOWNLOAD_URL
from src.platform.constants import WINTUN_ZIP_FILENAME
from src.platform.interfaces.tun_driver import ITunDriverAdapter
from src.services.installer.archive_extractor import ArchiveExtractor
from src.services.installer.file_downloader import FileDownloader
from src.utils.platform_utils import PlatformUtils


class WindowsTunDriverAdapter(ITunDriverAdapter):
    """Ensure wintun.dll is present for Windows TUN/VPN mode."""

    def __init__(
        self,
        downloader: Optional[FileDownloader] = None,
        extractor: Optional[ArchiveExtractor] = None,
        wintun_dll_path: str = WINTUN_DLL,
        download_url: str = WINTUN_DOWNLOAD_URL,
    ):
        self._downloader = downloader or FileDownloader()
        self._extractor = extractor or ArchiveExtractor(bin_dir=BIN_DIR)
        self._wintun_dll_path = wintun_dll_path
        self._download_url = download_url

    def is_driver_available(self) -> bool:
        """True if wintun.dll exists in the bin directory."""
        return os.path.exists(self._wintun_dll_path)

    def ensure_driver(
        self,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """Download and install wintun.dll if missing on Windows."""
        if self.is_driver_available():
            logger.info("[WindowsTunDriver] wintun.dll already present, skipping download")
            return True

        if progress_callback:
            progress_callback("Downloading wintun.dll for TUN/VPN mode...")

        try:
            wintun_zip = os.path.join(tempfile.gettempdir(), WINTUN_ZIP_FILENAME)
            logger.info(f"[WindowsTunDriver] Downloading wintun from {self._download_url}")
            if not self._downloader.download(self._download_url, wintun_zip):
                return False

            # Structure: wintun/bin/amd64/wintun.dll  (or arm64/)
            arch = PlatformUtils.get_architecture()
            arch_subdir = "amd64" if arch == "x86_64" else "arm64"
            member = f"wintun/bin/{arch_subdir}/wintun.dll"

            if not self._extractor.extract_member(wintun_zip, member, self._wintun_dll_path):
                return False

            try:
                os.remove(wintun_zip)
            except OSError as e:
                logger.warning(f"[WindowsTunDriver] Failed to remove temp file: {e}")

            if progress_callback:
                progress_callback("wintun.dll installed.")
            return True

        except Exception as e:
            logger.warning(f"[WindowsTunDriver] Failed to download wintun.dll: {e} (VPN mode may not work)")
            if progress_callback:
                progress_callback(f"wintun.dll download failed: {e}")
            return False


__all__ = ["WindowsTunDriverAdapter"]
