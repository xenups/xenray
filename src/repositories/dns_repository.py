"""DNS Repository - Concrete JSON-backed storage for DNS configuration."""
import os

from src.core.constants import RECENT_FILES_PATH
from src.repositories.file_utils import atomic_write_json, load_json_file


class DNSRepository:
    """Thin JSON wrapper for DNS configuration persistence."""

    def __init__(self, config_dir: str = None):
        self._config_dir = config_dir or os.path.dirname(RECENT_FILES_PATH)
        self._path = os.path.join(self._config_dir, "dns_config.json")

    def load(self) -> list:
        """Load DNS configuration."""
        defaults = [
            {"address": "1.1.1.1", "protocol": "udp", "domains": []},
            {"address": "8.8.8.8", "protocol": "udp", "domains": []},
        ]
        data = load_json_file(self._path, defaults)
        return data if isinstance(data, list) else defaults

    def save(self, dns_list: list) -> None:
        """Save DNS configuration."""
        atomic_write_json(self._path, dns_list)
