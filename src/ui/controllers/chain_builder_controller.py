"""Chain Builder Controller - manages outbound chain validation, profile loading, and chain persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from src.core.app_context import AppContext


class ChainBuilderController:
    """Controller handling outbound chain item validation and persistence."""

    def __init__(self, app_context: AppContext, existing_chain: Optional[dict] = None) -> None:
        self._app_context = app_context
        self._existing_chain = existing_chain

    def load_available_profiles(self) -> List[Dict[str, str]]:
        """Load all base profiles (excluding chains) for selection options."""
        profiles = []

        for profile in self._app_context.profiles.load_all():
            profiles.append(
                {
                    "id": profile.get("id"),
                    "name": profile.get("name", "Unknown"),
                    "source": "local",
                }
            )

        for sub in self._app_context.subscriptions.load_all():
            for profile in sub.get("profiles", []):
                profiles.append(
                    {
                        "id": profile.get("id"),
                        "name": f"{profile.get('name', 'Unknown')} ({sub.get('name', '')})",
                        "source": "subscription",
                    }
                )

        return profiles

    def validate_chain(self, name: str, profile_ids: List[str]) -> Tuple[bool, str]:
        """Validate chain name, item count, and routing loop constraints."""
        clean_name = name.strip()
        if not clean_name:
            return False, "add_dialog.required"

        if len(profile_ids) < 2:
            return False, "chain.validation.min_items"

        is_valid, error = self._app_context.validate_chain(profile_ids)
        if not is_valid:
            return False, error

        return True, ""

    def save_chain(self, name: str, profile_ids: List[str]) -> None:
        """Save new or updated outbound chain."""
        clean_name = name.strip()
        if self._existing_chain:
            self._app_context.update_chain(
                self._existing_chain["id"],
                {"name": clean_name, "items": profile_ids},
            )
        else:
            self._app_context.save_chain(clean_name, profile_ids)
