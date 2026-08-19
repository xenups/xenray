"""Archive extraction with Windows file-lock safety (rename-then-extract).

Owns: extracting the Xray-core zip into BIN_DIR with backup/rollback of files
that already exist, and the single-file member extraction used for wintun.dll.
"""

from __future__ import annotations

import os
import time
import zipfile
from typing import Optional

from loguru import logger

from src.platform.constants import (
    XRAY_EXTRACT_RETRIES,
    XRAY_EXTRACT_RETRY_DELAY_SECONDS,
)
from src.services.core_engines.xray_process_manager import XrayProcessManager

# Files the archive would overwrite are renamed to ``<name>.old`` so extraction
# never raises PermissionError on a locked binary.
OLD_SUFFIX = ".old"


class ArchiveExtractor:
    """Zip extraction with backup/rollback; kills the core first on Windows."""

    def __init__(self, bin_dir: str, process_manager: Optional[XrayProcessManager] = None):
        self._bin_dir = bin_dir
        self._process_manager = process_manager

    def extract_core(self, zip_path: str) -> bool:
        """Extract an Xray-core zip into the bin dir, replacing existing files.

        1. Kill any active core process (releases locked handles).
        2. Rename existing files the archive would overwrite to ``<name>.old``.
        3. Extract the new files.
        4. On success delete the ``.old`` backups; on failure roll them back.

        Returns:
            True if successful, False otherwise
        """
        try:
            if not os.path.exists(zip_path):
                logger.error(f"Zip file not found: {zip_path}")
                return False

            # 1. Kill the active core so xray.exe handles are released.
            self._kill_active_core()

            # 2. Identify archive entries and back up any that already exist.
            try:
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    entries = zip_ref.namelist()
            except zipfile.BadZipFile as e:
                logger.error(f"Corrupt zip file: {e}")
                return False

            backups: dict = {}
            for name in entries:
                if name.endswith("/"):
                    continue
                target = os.path.join(self._bin_dir, os.path.basename(name))
                if os.path.exists(target):
                    old_path = target + OLD_SUFFIX
                    try:
                        if os.path.exists(old_path):
                            os.remove(old_path)
                        os.rename(target, old_path)
                        backups[target] = old_path
                    except OSError:
                        backups[target] = None  # couldn't rename; leave in place

            # 3. Extract the new files.
            extracted = False
            for attempt in range(1, XRAY_EXTRACT_RETRIES + 1):
                try:
                    with zipfile.ZipFile(zip_path, "r") as zip_ref:
                        zip_ref.extractall(self._bin_dir)
                    extracted = True
                    break
                except (OSError, IOError) as e:
                    logger.warning(f"Extraction attempt {attempt}/{XRAY_EXTRACT_RETRIES} failed: {e}")
                    if attempt < XRAY_EXTRACT_RETRIES:
                        time.sleep(XRAY_EXTRACT_RETRY_DELAY_SECONDS)

            # Clean up temp zip
            try:
                os.remove(zip_path)
            except OSError as e:
                logger.warning(f"Failed to remove temp file: {e}")

            if extracted:
                # 4a. Success — drop the .old backups.
                for target, old_path in backups.items():
                    if old_path and os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except OSError:
                            pass
                return True

            # 4b. Rollback: restore the previous binaries so the app is not broken.
            logger.error("Xray extraction failed — rolling back previous binaries")
            for target, old_path in backups.items():
                if old_path and os.path.exists(old_path):
                    try:
                        os.replace(old_path, target)
                    except OSError as e:
                        logger.error(f"Rollback failed for {target}: {e}")
            return False
        except (zipfile.BadZipFile, OSError, IOError) as e:
            logger.error(f"Failed to extract Xray core: {e}")
            return False

    def _kill_active_core(self) -> None:
        """Route the process kill through the platform process layer."""
        try:
            self._process_manager.kill_all_core_instances()
        except Exception as e:
            logger.warning(f"[XrayInstaller] Failed to kill xray process: {e}")

    def extract_member(
        self,
        zip_path: str,
        member_name: str,
        dest_path: str,
    ) -> bool:
        """Extract a single member of *zip_path* to *dest_path*.

        Falls back to the first archive entry ending in the member's basename
        if the exact member path is absent.
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                entry = member_name if member_name in names else self._find_suffix_entry(names, member_name)
                if entry is None:
                    logger.error(f"{os.path.basename(member_name)} not found in downloaded archive")
                    return False
                with zf.open(entry) as src, open(dest_path, "wb") as dst:
                    dst.write(src.read())
            return True
        except (zipfile.BadZipFile, OSError, IOError) as e:
            logger.error(f"Failed to extract {os.path.basename(member_name)}: {e}")
            return False

    @staticmethod
    def _find_suffix_entry(names: list, member_name: str) -> Optional[str]:
        """First entry whose basename matches *member_name*'s basename."""
        basename = os.path.basename(member_name)
        for n in names:
            if os.path.basename(n) == basename:
                return n
        return None


def extract_member_to_file(
    zip_path: str,
    member_name: str,
    dest_path: str,
) -> bool:
    """Module-level convenience wrapper (lazy import safe)."""
    return ArchiveExtractor("").extract_member(zip_path, member_name, dest_path)


__all__ = ["ArchiveExtractor", "extract_member_to_file"]
