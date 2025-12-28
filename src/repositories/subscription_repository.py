"""Subscription Repository - Concrete JSON-backed storage for subscriptions."""
import os
import uuid
from datetime import datetime
from typing import Optional


from src.repositories.file_utils import atomic_write_json, load_json_file


class SubscriptionRepository:
    """Thin JSON wrapper for subscription persistence."""

    def __init__(self, config_dir: str):
        self._config_dir = config_dir
        self._path = os.path.join(config_dir, "subscriptions.json")

    def load_all(self) -> list[dict]:
        """Load all subscriptions, ensuring profiles have IDs."""
        subs = load_json_file(self._path, [])
        if not isinstance(subs, list):
            return []

        dirty = False
        for sub in subs:
            if "profiles" not in sub:
                sub["profiles"] = []

            if isinstance(sub["profiles"], list):
                for profile in sub["profiles"]:
                    if not profile.get("id"):
                        profile["id"] = str(uuid.uuid4())
                        dirty = True

        if dirty:
            atomic_write_json(self._path, subs)

        return subs

    def save(self, name: str, url: str) -> Optional[str]:
        """Save a new subscription. Returns subscription ID or None."""
        subs = self.load_all()
        sub_id = str(uuid.uuid4())
        subs.append(
            {
                "id": sub_id,
                "name": name,
                "url": url,
                "profiles": [],
                "created_at": str(datetime.now()),
            }
        )
        if atomic_write_json(self._path, subs):
            return sub_id
        return None

    def update(self, subscription: dict) -> None:
        """Update an existing subscription."""
        subs = self.load_all()
        for i, sub in enumerate(subs):
            if sub.get("id") == subscription.get("id"):
                subs[i] = subscription
                break
        atomic_write_json(self._path, subs)

    def delete(self, sub_id: str) -> None:
        """Delete a subscription by ID."""
        subs = self.load_all()
        subs = [s for s in subs if s.get("id") != sub_id]
        atomic_write_json(self._path, subs)

    def get_by_id(self, sub_id: str) -> Optional[dict]:
        """Get a subscription by ID."""
        if not sub_id:
            return None
        for sub in self.load_all():
            if sub.get("id") == sub_id:
                return sub
        return None
