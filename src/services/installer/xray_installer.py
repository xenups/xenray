"""Xray Installer Service — orchestration facade.

Single responsibility: drive the install pipeline (download → stop service →
extract → TUN driver). The per-step logic lives in dedicated components:

    FileDownloader          (src/services/file_downloader.py)         — streaming download
    ArchiveExtractor        (src/services/archive_extractor.py)       — lock-safe extraction
    Platform TUN Driver     (src/platform/factory.py)                 — driver bootstrap
    XrayVersionChecker      (src/services/xray_version_checker.py)    — version facts

Process kills route through the platform process layer (XrayProcessManager /
get_process_adapter), never raw subprocess here.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from loguru import logger

from src.core.constants import BIN_DIR, XRAY_EXECUTABLE
from src.platform.factory import get_tun_driver_adapter
from src.services.core_engines.xray_process_manager import XrayProcessManager
from src.services.installer.archive_extractor import ArchiveExtractor
from src.services.installer.file_downloader import FileDownloader
from src.services.installer.xray_version_checker import XrayVersionChecker


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
            zip_path = FileDownloader().download_xray_core(
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
            if not ArchiveExtractor(
                bin_dir=BIN_DIR,
                process_manager=XrayProcessManager(),
            ).extract_core(zip_path):
                return False

            # 4. Ensure platform TUN driver is present (required for VPN/TUN mode)
            get_tun_driver_adapter().ensure_driver(progress_callback)

            if progress_callback:
                progress_callback("Installation complete!")
            return True
        except Exception as e:
            logger.error(f"Xray install failed: {e}")
            if progress_callback:
                progress_callback(f"Installation failed: {e}")
            return False

    # ------------------------------------------------------------------
    # TUN driver management
    # ------------------------------------------------------------------

    @staticmethod
    def is_tun_driver_present() -> bool:
        """Check if platform TUN driver is present."""
        return get_tun_driver_adapter().is_driver_available()

    @staticmethod
    def is_wintun_present() -> bool:
        """Check if TUN driver is present (backward-compat alias)."""
        return get_tun_driver_adapter().is_driver_available()

    # ------------------------------------------------------------------
    # version checks
    # ------------------------------------------------------------------

    @staticmethod
    def get_local_version() -> Optional[str]:
        """
        Get installed Xray version.
        Returns version string (e.g., "1.8.4") or None.
        """
        return XrayVersionChecker(executable_path=XRAY_EXECUTABLE).get_local_version()

    @staticmethod
    def check_for_updates(
        include_prerelease: bool = True,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Check for updates via GitHub API.

        Args:
            include_prerelease: If True, include pre-release versions (default: True).

        Returns: (update_available, current_version, latest_version)
        """
        checker = XrayVersionChecker(executable_path=XRAY_EXECUTABLE)
        return checker.check_for_updates(
            include_prerelease=include_prerelease,
            current_version=XrayInstallerService.get_local_version(),
        )
