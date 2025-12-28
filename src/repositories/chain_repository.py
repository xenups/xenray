"""Chain Repository - Concrete JSON-backed storage for chains."""
import os
import uuid
from datetime import datetime
from typing import Optional

from src.core.constants import RECENT_FILES_PATH
from src.core.logger import logger
from src.repositories.file_utils import atomic_write_json, load_json_file


class ChainRepository:
    """Thin JSON wrapper for chain persistence."""

    def __init__(self, config_dir: str = None):
        self._config_dir = config_dir or os.path.dirname(RECENT_FILES_PATH)
        self._path = os.path.join(self._config_dir, "chains.json")

    def load_all(self) -> list[dict]:
        """Load all chains (raw, without validation)."""
        data = load_json_file(self._path, [])
        return data if isinstance(data, list) else []

    def save(self, name: str, profile_ids: list[str]) -> Optional[str]:
        """Save a new chain. Returns chain ID or None."""
        if not name:
            logger.warning("Invalid chain name")
            return None

        chains = self.load_all()
        chain_id = str(uuid.uuid4())
        chains.append(
            {
                "id": chain_id,
                "name": name,
                "items": profile_ids,
                "created_at": str(datetime.now()),
            }
        )

        if atomic_write_json(self._path, chains):
            return chain_id
        logger.error("Failed to save chain")
        return None

    def update(self, chain_id: str, updates: dict) -> bool:
        """Update an existing chain."""
        if not chain_id:
            return False

        chains = self.load_all()
        for chain in chains:
            if chain.get("id") == chain_id:
                chain.update(updates)
                return atomic_write_json(self._path, chains)
        return False

    def delete(self, chain_id: str) -> None:
        """Delete a chain by ID."""
        if not chain_id:
            return
        chains = self.load_all()
        chains = [c for c in chains if c.get("id") != chain_id]
        atomic_write_json(self._path, chains)

    def get_by_id(self, chain_id: str) -> Optional[dict]:
        """Get a chain by ID (raw, without validation)."""
        if not chain_id:
            return None
        for chain in self.load_all():
            if chain.get("id") == chain_id:
                return chain
        return None

    def is_chain(self, item_id: str) -> bool:
        """Check if an ID refers to a chain."""
        if not item_id:
            return False
        return any(c.get("id") == item_id for c in self.load_all())

    def load_enriched(self, profile_resolver) -> list[dict]:
        """Load chains with validation status.

        Args:
            profile_resolver: Object with resolve_for_validation(profile_id) method
        """
        chains = self.load_all()
        for chain in chains:
            missing = [pid for pid in chain.get("items", []) if not profile_resolver.resolve_for_validation(pid)]
            chain["valid"] = len(missing) == 0
            chain["missing_profiles"] = missing
        return chains

    def get_enriched_by_id(self, chain_id: str, profile_resolver) -> Optional[dict]:
        """Get a chain by ID with validation status."""
        if not chain_id:
            return None
        for chain in self.load_enriched(profile_resolver):
            if chain.get("id") == chain_id:
                return chain
        return None

    def save_validated(self, name: str, profile_ids: list[str], profile_resolver) -> Optional[str]:
        """Save a new chain with validation. Returns chain ID or None."""
        from src.core.validators import ValidationError, validate_chain_items

        if not name or not isinstance(name, str):
            logger.warning("Invalid chain name")
            return None

        try:
            validate_chain_items(profile_ids, self.is_chain, profile_resolver)
        except ValidationError as e:
            logger.warning(f"Chain validation failed: {e}")
            return None

        return self.save(name, profile_ids)

    def update_validated(self, chain_id: str, updates: dict, profile_resolver) -> bool:
        """Update an existing chain with validation."""
        from src.core.validators import ValidationError, validate_chain_items

        if not chain_id:
            return False

        if "items" in updates:
            try:
                validate_chain_items(updates["items"], self.is_chain, profile_resolver)
            except ValidationError as e:
                logger.warning(f"Chain update validation failed: {e}")
                return False

        return self.update(chain_id, updates)

    def validate(self, profile_ids: list[str], profile_resolver) -> tuple[bool, str]:
        """Validate a chain configuration. Returns (is_valid, error_message)."""
        from src.core.validators import ValidationError, validate_chain_items

        try:
            validate_chain_items(profile_ids, self.is_chain, profile_resolver)
            return True, ""
        except ValidationError as e:
            return False, str(e)
