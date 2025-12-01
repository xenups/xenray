"""Configuration management for xenray."""

import json
import logging
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class Config:
    """Manages xenray configuration."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration.

        Args:
            config_path: Path to configuration file. If None, uses default path.
        """
        self.config_path = config_path or self._get_default_config_path()
        self.config_data: Dict[str, Any] = {}
        self._load_config()

    @staticmethod
    def _get_default_config_path() -> Path:
        """Get default configuration path based on platform."""
        system = platform.system()
        home = Path.home()

        if system == "Windows":
            config_dir = home / "AppData" / "Roaming" / "xenray"
        elif system == "Darwin":
            config_dir = home / "Library" / "Application Support" / "xenray"
        else:  # Linux and others
            config_dir = home / ".config" / "xenray"

        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "config.json"

    def _load_config(self) -> None:
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config_data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading config: {e}. Using default configuration.")
                self.config_data = self._get_default_config()
        else:
            self.config_data = self._get_default_config()
            self.save()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "xray_binary": self._get_default_xray_binary(),
            "log_level": "info",
            "auto_reconnect": True,
            "connection_timeout": 10,
            "servers": [],
            "active_server": None,
            "inbound": {
                "listen": "127.0.0.1",
                "port": 10808,
                "protocol": "socks",
            },
        }

    @staticmethod
    def _get_default_xray_binary() -> str:
        """Get default Xray binary path based on platform."""
        system = platform.system()
        if system == "Windows":
            return "xray.exe"
        else:
            return "xray"

    def save(self) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config_data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value.

        Args:
            key: Configuration key (supports dot notation, e.g., 'inbound.port')
            default: Default value if key doesn't exist

        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self.config_data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Set configuration value.

        Args:
            key: Configuration key (supports dot notation)
            value: Value to set
        """
        keys = key.split(".")
        data = self.config_data
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        data[keys[-1]] = value

    def add_server(self, server: Dict[str, Any]) -> None:
        """Add a server configuration.

        Args:
            server: Server configuration dictionary
        """
        servers = self.config_data.get("servers", [])
        servers.append(server)
        self.config_data["servers"] = servers
        self.save()

    def remove_server(self, server_id: str) -> bool:
        """Remove a server configuration.

        Args:
            server_id: Server ID to remove

        Returns:
            True if server was removed, False otherwise
        """
        servers = self.config_data.get("servers", [])
        original_len = len(servers)
        servers = [s for s in servers if s.get("id") != server_id]
        if len(servers) < original_len:
            self.config_data["servers"] = servers
            self.save()
            return True
        return False

    def get_servers(self) -> List[Dict[str, Any]]:
        """Get all configured servers.

        Returns:
            List of server configurations
        """
        return self.config_data.get("servers", [])

    def set_active_server(self, server_id: Optional[str]) -> None:
        """Set active server.

        Args:
            server_id: Server ID to set as active, or None to clear
        """
        self.config_data["active_server"] = server_id
        self.save()

    def get_active_server(self) -> Optional[Dict[str, Any]]:
        """Get active server configuration.

        Returns:
            Active server configuration or None
        """
        server_id = self.config_data.get("active_server")
        if server_id:
            servers = self.get_servers()
            for server in servers:
                if server.get("id") == server_id:
                    return server
        return None

    def import_config(self, config_file: Path, file_format: str = "json") -> bool:
        """Import configuration from file.

        Args:
            config_file: Path to configuration file
            file_format: File format ('json' or 'yaml')

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                if file_format.lower() == "yaml":
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)

            # Merge with existing config
            if isinstance(data, dict):
                self.config_data.update(data)
                self.save()
                return True
        except Exception as e:
            logger.error(f"Error importing config: {e}")
        return False

    def export_config(self, output_file: Path, file_format: str = "json") -> bool:
        """Export configuration to file.

        Args:
            output_file: Path to output file
            file_format: File format ('json' or 'yaml')

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                if file_format.lower() == "yaml":
                    yaml.dump(self.config_data, f, default_flow_style=False)
                else:
                    json.dump(self.config_data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error exporting config: {e}")
        return False
