"""Protocols for type-safe dependency injection."""
from typing import Optional, Protocol


class ProfileLookup(Protocol):
    """Protocol for profile lookup capability."""

    def get_profile_by_id(self, profile_id: str) -> Optional[dict]:
        """Get a profile by ID. Returns None if not found."""
        ...
