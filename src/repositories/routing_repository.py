"""Routing Repository - Concrete JSON-backed storage for routing configuration."""
import os

from src.core.constants import RECENT_FILES_PATH
from src.repositories.file_utils import atomic_write_json, load_json_file


class RoutingRepository:
    """Thin JSON wrapper for routing rules and toggles persistence."""

    def __init__(self, config_dir: str = None):
        self._config_dir = config_dir or os.path.dirname(RECENT_FILES_PATH)

    def load_rules(self) -> dict:
        """Load routing rules."""
        defaults = {"direct": [], "proxy": [], "block": []}
        path = os.path.join(self._config_dir, "routing_rules.json")
        data = load_json_file(path, defaults)
        return data if isinstance(data, dict) else defaults

    def save_rules(self, rules: dict) -> None:
        """Save routing rules."""
        path = os.path.join(self._config_dir, "routing_rules.json")
        atomic_write_json(path, rules)

    def load_toggles(self) -> dict:
        """Load routing toggle states."""
        defaults = {
            "block_udp_443": False,
            "block_ads": False,
            "direct_private_ips": True,
            "direct_local_domains": True,
        }
        path = os.path.join(self._config_dir, "routing_toggles.json")
        data = load_json_file(path, defaults)
        return data if isinstance(data, dict) else defaults

    def save_toggle(self, name: str, value: bool) -> None:
        """Save a single routing toggle."""
        toggles = self.load_toggles()
        toggles[name] = value
        path = os.path.join(self._config_dir, "routing_toggles.json")
        atomic_write_json(path, toggles)
