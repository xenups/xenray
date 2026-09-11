"""Version-check responsibility for sing-box core.

Owns: reading the installed sing-box version from binary and comparing it
against the latest GitHub release.
"""

from __future__ import annotations

import os
import subprocess
from typing import Optional

import requests
from loguru import logger

from src.core.constants import SINGBOX_EXECUTABLE

SINGBOX_GITHUB_RELEASES_API_URL = "https://api.github.com/repos/SagerNet/sing-box/releases"


class SingboxVersionChecker:
    """Local/remote sing-box version facts."""

    def __init__(
        self,
        executable_path: str = SINGBOX_EXECUTABLE,
        subprocess_timeout: float = 5.0,
    ):
        self._executable_path = executable_path
        self._subprocess_timeout = subprocess_timeout

    def get_local_version(self) -> Optional[str]:
        """Get installed sing-box version string (e.g. "1.14.0") or None."""
        if not self._executable_path or not os.path.exists(self._executable_path):
            return None

        try:
            from src.platform.factory import get_process_adapter

            adapter = get_process_adapter()
            result = subprocess.run(
                [self._executable_path, "version"],
                capture_output=True,
                text=True,
                timeout=self._subprocess_timeout,
                creationflags=adapter.get_subprocess_flags(),
                startupinfo=adapter.get_startupinfo(),
            )

            if result.returncode == 0:
                first_line = result.stdout.splitlines()[0]
                # e.g. "sing-box version 1.14.0"
                parts = first_line.split()
                if len(parts) >= 3:
                    return parts[2].lstrip("v")
                if len(parts) >= 2:
                    return parts[1].lstrip("v")
            return None
        except Exception as e:
            logger.warning(f"Failed to check sing-box version: {e}")
            return None

    def check_for_updates(
        self,
        include_prerelease: bool = True,
        current_version: Optional[str] = None,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Check for updates via GitHub releases API with direct-connection fallback.

        Returns: (update_available, current_version, latest_version)
        """
        if current_version is None:
            current_version = self.get_local_version()

        try:
            try:
                response = requests.get(SINGBOX_GITHUB_RELEASES_API_URL, timeout=(10, 15))
                response.raise_for_status()
            except (requests.exceptions.RequestException, Exception) as net_err:
                logger.warning(
                    f"[SingboxVersionChecker] Primary request failed: {net_err}. Retrying with direct connection..."
                )
                session = requests.Session()
                session.trust_env = False
                session.proxies = {"http": None, "https": None}
                response = session.get(SINGBOX_GITHUB_RELEASES_API_URL, timeout=(10, 15))
                response.raise_for_status()

            data = response.json()
            if not data or not isinstance(data, list):
                logger.error("Unexpected response format from GitHub API")
                return False, current_version, None

            target_release = None
            if include_prerelease:
                target_release = data[0]
            else:
                for rel in data:
                    if not rel.get("prerelease", False):
                        target_release = rel
                        break

            if not target_release:
                logger.warning("No suitable release found in GitHub API response")
                return False, current_version, None

            tag_name = target_release.get("tag_name", "")
            latest_version = tag_name.lstrip("v")
            current_version_normalized = current_version.lstrip("v") if current_version else None

            logger.info(f"Singbox version check — current: {current_version_normalized}, latest: {latest_version}")

            if not current_version_normalized:
                return True, None, latest_version

            try:
                from packaging.version import parse as parse_version

                if parse_version(latest_version) > parse_version(current_version_normalized):
                    return True, current_version_normalized, latest_version
            except Exception:
                if current_version_normalized != latest_version:
                    return True, current_version_normalized, latest_version

            return False, current_version_normalized, latest_version

        except Exception as e:
            logger.error(f"Failed to check for sing-box updates: {e}")
            return False, current_version, None


__all__ = ["SingboxVersionChecker", "SINGBOX_GITHUB_RELEASES_API_URL"]
