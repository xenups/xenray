"""Tests for configuration management."""

import tempfile
from pathlib import Path

import pytest

from xenray.core.config import Config


@pytest.fixture
def temp_config_file():
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        config_path = Path(f.name)
    yield config_path
    if config_path.exists():
        config_path.unlink()


def test_config_initialization(temp_config_file):
    """Test config initialization."""
    config = Config(temp_config_file)
    assert config.config_path == temp_config_file
    assert isinstance(config.config_data, dict)


def test_config_default_values(temp_config_file):
    """Test default configuration values."""
    config = Config(temp_config_file)
    assert config.get("log_level") == "info"
    assert config.get("auto_reconnect") is True
    assert config.get("inbound.port") == 10808
    assert config.get("inbound.protocol") == "socks"


def test_config_get_set(temp_config_file):
    """Test getting and setting config values."""
    config = Config(temp_config_file)

    # Test simple key
    config.set("test_key", "test_value")
    assert config.get("test_key") == "test_value"

    # Test nested key
    config.set("nested.key", "nested_value")
    assert config.get("nested.key") == "nested_value"

    # Test default value
    assert config.get("nonexistent_key", "default") == "default"


def test_config_add_remove_server(temp_config_file):
    """Test adding and removing servers."""
    config = Config(temp_config_file)

    # Add server
    server = {
        "id": "test-server",
        "name": "Test Server",
        "address": "example.com",
        "port": 443,
        "protocol": "vless",
        "uuid": "test-uuid",
    }
    config.add_server(server)

    # Check server was added
    servers = config.get_servers()
    assert len(servers) == 1
    assert servers[0]["id"] == "test-server"

    # Remove server
    assert config.remove_server("test-server") is True
    assert len(config.get_servers()) == 0

    # Try removing non-existent server
    assert config.remove_server("nonexistent") is False


def test_config_active_server(temp_config_file):
    """Test active server management."""
    config = Config(temp_config_file)

    # Add servers
    server1 = {"id": "server1", "name": "Server 1", "address": "example1.com", "port": 443}
    server2 = {"id": "server2", "name": "Server 2", "address": "example2.com", "port": 443}
    config.add_server(server1)
    config.add_server(server2)

    # Set active server
    config.set_active_server("server1")
    active = config.get_active_server()
    assert active is not None
    assert active["id"] == "server1"

    # Change active server
    config.set_active_server("server2")
    active = config.get_active_server()
    assert active["id"] == "server2"

    # Clear active server
    config.set_active_server(None)
    assert config.get_active_server() is None


def test_config_persistence(temp_config_file):
    """Test configuration persistence."""
    # Create and modify config
    config1 = Config(temp_config_file)
    config1.set("test_key", "test_value")
    config1.save()

    # Load config again
    config2 = Config(temp_config_file)
    assert config2.get("test_key") == "test_value"


def test_config_export_import(temp_config_file):
    """Test config export and import."""
    config = Config(temp_config_file)
    config.set("custom_key", "custom_value")

    # Export
    export_file = temp_config_file.parent / "export.json"
    try:
        assert config.export_config(export_file, "json") is True
        assert export_file.exists()

        # Import into new config
        new_config_file = temp_config_file.parent / "new_config.json"
        new_config = Config(new_config_file)
        assert new_config.import_config(export_file, "json") is True
        assert new_config.get("custom_key") == "custom_value"

        if new_config_file.exists():
            new_config_file.unlink()
    finally:
        if export_file.exists():
            export_file.unlink()
