"""Singbox Installer Service — orchestration facade.

Drives the install/update pipeline for sing-box core:
1. Permission verification.
2. Download sing-box release to staging temp directory.
3. Stop sing-box service.
4. Extract, verify, and atomically replace the binary using ArchiveExtractor.
5. Bootstrap platform TUN driver if required.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from loguru import logger

from src.core.constants import BIN_DIR, SINGBOX_EXECUTABLE
from src.platform.factory import get_tun_driver_adapter
from src.services.core_engines.singbox_process_manager import SingboxProcessManager
from src.services.installer.archive_extractor import ArchiveExtractor, CorePermissionError
from src.services.installer.file_downloader import FileDownloader
from src.services.installer.singbox_version_checker import SingboxVersionChecker


class SingboxInstallerService:
    """Manages sing-box installation and updates."""

    @staticmethod
    def is_installed() -> bool:
        """Check if sing-box is installed."""
        return os.path.exists(SINGBOX_EXECUTABLE)

    @staticmethod
    def install(
        progress_callback: Optional[Callable[[str], None]] = None,
        stop_service_callback: Optional[Callable[[], None]] = None,
        target_version: Optional[str] = None,
    ) -> bool:
        """Install or update sing-box binary safely.

        Args:
            progress_callback: Function to report progress messages.
            stop_service_callback: Function to stop active connection/core before file replacement.
            target_version: Specific version string (e.g. "1.14.0").

        Returns:
            True if successful, False otherwise.
        """
        try:
            os.makedirs(BIN_DIR, exist_ok=True)

            extractor = ArchiveExtractor(
                bin_dir=BIN_DIR,
                process_manager=SingboxProcessManager,
            )

            # 0. Check write permissions before starting download
            writable, perm_msg = extractor.verify_write_permissions()
            if not writable:
                err = perm_msg or "Write access to binary directory denied"
                if progress_callback:
                    progress_callback(err)
                raise CorePermissionError(err)

            # 1. Download sing-box to staging temp location first
            if progress_callback:
                progress_callback("Downloading Sing-box Core...")
            archive_path = FileDownloader().download_singbox_core(
                progress_callback=progress_callback,
                target_version=target_version,
            )
            if not archive_path:
                return False

            # 2. STOP singbox service AFTER download, BEFORE file replacement
            if progress_callback:
                progress_callback("Stopping Sing-box service...")
            if stop_service_callback:
                try:
                    stop_service_callback()
                except Exception as e:
                    logger.warning(f"Error stopping service: {e}")

            # 3. Extract and atomically replace binary
            if progress_callback:
                progress_callback("Installing Sing-box Core...")
            if not extractor.extract_core(archive_path, target_binary_name=os.path.basename(SINGBOX_EXECUTABLE)):
                return False

            # 4. Ensure platform TUN driver is present
            get_tun_driver_adapter().ensure_driver(progress_callback)

            if progress_callback:
                progress_callback("Installation complete!")
            return True
        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"Sing-box install failed: {e}")
            if progress_callback:
                progress_callback(f"Installation failed: {e}")
            return False

    @staticmethod
    def get_local_version() -> Optional[str]:
        """Get installed sing-box version."""
        return SingboxVersionChecker(executable_path=SINGBOX_EXECUTABLE).get_local_version()

    @staticmethod
    def check_for_updates(
        include_prerelease: bool = True,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Check for sing-box updates via GitHub API."""
        checker = SingboxVersionChecker(executable_path=SINGBOX_EXECUTABLE)
        return checker.check_for_updates(
            include_prerelease=include_prerelease,
            current_version=SingboxInstallerService.get_local_version(),
        )


__all__ = ["SingboxInstallerService"]
