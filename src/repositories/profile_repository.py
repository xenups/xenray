"""Profile Repository - Concrete JSON-backed storage for profiles."""
import os
import uuid
from datetime import datetime
from typing import Optional

from src.core.logger import logger
from src.repositories.file_utils import atomic_write_json, load_json_file


class ProfileRepository:
    """Thin JSON wrapper for profile persistence."""

    def __init__(self, config_dir: str):
        self._path = os.path.join(config_dir, "profiles.json")

    def load_all(self) -> list[dict]:
        """Load all profiles."""
        data = load_json_file(self._path, [])
        return data if isinstance(data, list) else []

    def save(self, name: str, config: dict) -> Optional[str]:
        """Save a new profile. Returns profile ID or None."""
        if not name or not isinstance(name, str):
            logger.warning("Invalid profile name")
            return None
        if not isinstance(config, dict):
            logger.warning("Invalid profile config")
            return None

        profiles = self.load_all()
        profile_id = str(uuid.uuid4())
        profiles.append(
            {
                "id": profile_id,
                "name": name,
                "config": config,
                "created_at": str(datetime.now()),
            }
        )

        if atomic_write_json(self._path, profiles):
            return profile_id
        logger.error("Failed to save profile")
        return None

    def update(self, profile_id: str, updates: dict) -> bool:
        """Update an existing profile."""
        if not profile_id:
            return False

        profiles = self.load_all()
        updated = False

        for p in profiles:
            if p.get("id") == profile_id:
                p.update(updates)
                updated = True
                break

        if updated:
            if not atomic_write_json(self._path, profiles):
                logger.error("Failed to save updated profile")
                return False
            return True
        return False

    def delete(self, profile_id: str) -> None:
        """Delete a profile by ID."""
        if not profile_id:
            return

        profiles = self.load_all()
        profiles = [p for p in profiles if p.get("id") != profile_id]

        if not atomic_write_json(self._path, profiles):
            logger.error("Failed to delete profile")

    def get_by_id(self, profile_id: str) -> Optional[dict]:
        """Get a single profile by ID."""
        if not profile_id:
            return None
        for p in self.load_all():
            if p.get("id") == profile_id:
                return p
        return None
