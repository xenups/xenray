"""
Rule Update Service.

Downloads geoip.dat and geosite.dat from Chocolate4U/Iran-v2ray-rules
so that Xray can use up-to-date Iranian-specific routing rules.
"""

import os
import tempfile
from typing import Callable, Optional

import requests
from loguru import logger

from src.core.constants import RULES_DIR

GITHUB_REPO = "Chocolate4U/Iran-v2ray-rules"
GEOIP_URL = f"https://github.com/{GITHUB_REPO}/releases/latest/download/geoip.dat"
GEOSITE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest/download/geosite.dat"
CONNECT_TIMEOUT = 15.0
READ_TIMEOUT = 60.0
CHUNK_SIZE = 65536
MIN_FILE_SIZE = 1024
MAX_RETRIES = 3


class RuleUpdateService:
    """Downloads and installs geoip.dat / geosite.dat rule files."""

    @staticmethod
    def get_rules_dir() -> str:
        """Return the directory where rule files should be stored."""
        os.makedirs(RULES_DIR, exist_ok=True)
        return RULES_DIR

    @staticmethod
    def get_local_rule_version(name: str) -> Optional[str]:
        """
        Read the version marker file for a rule asset.

        Args:
            name: "geoip" or "geosite"

        Returns:
            Version string or None if not available
        """
        marker = os.path.join(RULES_DIR, f".{name}_version")
        if os.path.exists(marker):
            with open(marker) as f:
                return f.read().strip()
        return None

    @staticmethod
    def _save_version_marker(name: str, version: str):
        """Write version marker file so we can track what's installed."""
        marker = os.path.join(RULES_DIR, f".{name}_version")
        with open(marker, "w") as f:
            f.write(version)

    @staticmethod
    def get_latest_rule_version(name: str) -> Optional[str]:
        """
        Query GitHub API for the latest release tag of Iran-v2ray-rules.

        Args:
            name: "geoip" or "geosite"

        Returns:
            Version tag string (e.g. "2025.01.15") or None on failure
        """
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            resp = requests.get(url, timeout=CONNECT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            return data.get("tag_name", "").lstrip("v")
        except Exception as e:
            logger.warning(f"[RuleUpdateService] Failed to check latest version for {name}: {e}")
            return None

    @staticmethod
    def download_rule(
        name: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Optional[str]:
        """
        Download a rule file (geoip.dat or geosite.dat) from GitHub releases.

        Args:
            name: "geoip" or "geosite"
            progress_callback: Called with status messages

        Returns:
            Path to downloaded file, or None on failure
        """
        url = GEOIP_URL if name == "geoip" else GEOSITE_URL
        filename = f"{name}.dat"

        if progress_callback:
            progress_callback(f"Downloading {filename}...")

        dest_dir = RuleUpdateService.get_rules_dir()
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f"_{filename}")
        os.close(tmp_fd)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(
                    url,
                    stream=True,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                )
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(tmp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total_size > 0:
                                pct = int(downloaded * 100 / total_size)
                                progress_callback(f"Downloading {filename}... {pct}%")

                if downloaded < MIN_FILE_SIZE:
                    raise ValueError(f"Downloaded file too small: {downloaded} bytes")

                dest_path = os.path.join(dest_dir, filename)
                os.replace(tmp_path, dest_path)
                logger.info(f"[RuleUpdateService] Installed {filename} ({downloaded} bytes)")

                if progress_callback:
                    progress_callback(f"Installed {filename}")

                return dest_path

            except Exception as e:
                logger.warning(f"[RuleUpdateService] Attempt {attempt}/{MAX_RETRIES} failed for {filename}: {e}")
                if progress_callback:
                    progress_callback(f"Retrying {filename}... ({attempt}/{MAX_RETRIES})")

        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

        logger.error(f"[RuleUpdateService] Failed to download {filename} after {MAX_RETRIES} attempts")
        return None

    @staticmethod
    def update_rules(
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        Download both geoip.dat and geosite.dat.

        Args:
            progress_callback: Called with status messages

        Returns:
            True if both files were updated successfully
        """
        success = True
        for name in ("geoip", "geosite"):
            result = RuleUpdateService.download_rule(name, progress_callback)
            if result is None:
                success = False
        return success

    @staticmethod
    def check_for_updates() -> tuple[bool, Optional[str], Optional[str]]:
        """
        Check if newer rule files are available on GitHub.

        Returns:
            Tuple (available, local_version, latest_version)
            available: True if an update is available
            local_version: Currently installed version string (or None)
            latest_version: Latest available version string (or None)
        """
        # We use a combined approach — check latest release tag on GitHub
        latest = RuleUpdateService.get_latest_rule_version("geoip")
        if not latest:
            return False, None, None

        local = RuleUpdateService.get_local_rule_version("geoip")
        # Simple string comparison — if the tag differs, update is available
        available = (local != latest) if local else True
        return available, local, latest
