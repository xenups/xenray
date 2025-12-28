"""Recent Files Repository - Concrete JSON-backed storage for recent files."""
import os
from typing import Optional

from src.core.constants import LAST_FILE_PATH, MAX_RECENT_FILES, RECENT_FILES_PATH
from src.core.logger import logger
from src.repositories.file_utils import atomic_write, atomic_write_json, load_json_file


def _validate_file_path(file_path: str) -> bool:
    """Validate file path to prevent path traversal attacks."""
    if not file_path or not isinstance(file_path, str):
        return False
    normalized = os.path.normpath(file_path)
    if ".." in normalized or normalized.startswith("/") or normalized.startswith("\\"):
        return False
    return True


class RecentFilesRepository:
    """Thin JSON wrapper for recent files persistence."""

    def __init__(self):
        self._recent_path = RECENT_FILES_PATH
        self._last_path = LAST_FILE_PATH

    def get_all(self) -> list[str]:
        """Get list of recent files."""
        data = load_json_file(self._recent_path, [])
        if not isinstance(data, list):
            return []
        return [f for f in data if isinstance(f, str) and _validate_file_path(f)]

    def add(self, file_path: str) -> None:
        """Add file to recent list."""
        if not _validate_file_path(file_path):
            logger.warning(f"Invalid file path for recent files: {file_path}")
            return

        recent = self.get_all()
        if file_path in recent:
            recent.remove(file_path)
        recent.insert(0, file_path)

        if len(recent) > MAX_RECENT_FILES:
            recent = recent[:MAX_RECENT_FILES]

        atomic_write_json(self._recent_path, recent)
        self.set_last_selected(file_path)

    def remove(self, file_path: str) -> None:
        """Remove file from recent list."""
        if not _validate_file_path(file_path):
            return

        recent = self.get_all()
        if file_path in recent:
            recent.remove(file_path)
            atomic_write_json(self._recent_path, recent)

    def get_last_selected(self) -> Optional[str]:
        """Get last selected file path."""
        if not os.path.exists(self._last_path):
            return None
        try:
            with open(self._last_path, "r", encoding="utf-8") as f:
                path = f.read().strip()
                return path if _validate_file_path(path) else None
        except (OSError, IOError):
            return None

    def set_last_selected(self, file_path: str) -> None:
        """Set last selected file path."""
        if not _validate_file_path(file_path):
            return
        atomic_write(self._last_path, file_path)
