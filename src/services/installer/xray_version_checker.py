"""Version-check responsibility — local binary version and GitHub release check.

Owns: reading the installed Xray version from the binary and comparing it
against the latest GitHub release (semantic or string fallback).
"""

from __future__ import annotations

import subprocess
from typing import Optional

import requests
from loguru import logger

from src.platform.constants import XRAY_GITHUB_RELEASES_API_URL


class XrayVersionChecker:
    """Local/remote Xray version facts."""

    def __init__(
        self,
        executable_path: str,
        subprocess_timeout: float = 5.0,
    ):
        self._executable_path = executable_path
        self._subprocess_timeout = subprocess_timeout

    # -- local ----------------------------------------------------------
    def get_local_version(self) -> Optional[str]:
        """Installed Xray version (e.g. "1.8.4") or None."""
        if not self._executable_path or not self._check_executable_exists():
            return None

        try:
            from src.platform.factory import get_process_adapter

            adapter = get_process_adapter()
            result = subprocess.run(
                [self._executable_path, "-version"],
                capture_output=True,
                text=True,
                timeout=self._subprocess_timeout,
                creationflags=adapter.get_subprocess_flags(),
                startupinfo=adapter.get_startupinfo(),
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

    def _check_executable_exists(self) -> bool:
        import os

        return os.path.exists(self._executable_path)

    # -- remote ---------------------------------------------------------
    def check_for_updates(
        self,
        include_prerelease: bool = True,
        current_version: Optional[str] = None,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Check for updates via the GitHub releases API.

        Returns: (update_available, current_version, latest_version)
        """
        if current_version is None:
            current_version = self.get_local_version()

        try:
            response = requests.get(XRAY_GITHUB_RELEASES_API_URL, timeout=(10, 15))
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

            tag_name = target_release.get("tag_name", "")  # e.g. "v1.8.4" or "v26.7.11"
            latest_version = tag_name.lstrip("v")
            current_version_normalized = current_version.lstrip("v") if current_version else None

            logger.info(f"Version check — current: {current_version_normalized}, latest: {latest_version}")

            if not current_version_normalized:
                logger.info("No current version found, update available")
                return True, None, latest_version

            try:
                from packaging.version import parse as parse_version

                if parse_version(latest_version) > parse_version(current_version_normalized):
                    logger.info(f"Update available: {current_version_normalized} -> {latest_version}")
                    return True, current_version_normalized, latest_version
            except Exception:
                logger.warning("Semantic version parsing failed, falling back to string comparison")
                if current_version_normalized != latest_version:
                    logger.info(f"Update available (string cmp): {current_version_normalized} -> {latest_version}")
                    return True, current_version_normalized, latest_version

            logger.info("Already up to date")
            return False, current_version_normalized, latest_version

        except Exception as e:
            logger.error(f"Failed to check for updates: {e}")
            return False, current_version, None
