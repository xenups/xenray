"""Tests for Xray manager."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from xenray.core.config import Config
from xenray.core.xray_manager import XrayManager


@pytest.fixture
def temp_config():
    """Create a temporary config."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        config_path = Path(f.name)
    config = Config(config_path)
    yield config
    if config_path.exists():
        config_path.unlink()


@pytest.fixture
def manager(temp_config):
    """Create an XrayManager instance."""
    return XrayManager(temp_config)


def test_manager_initialization(temp_config):
    """Test manager initialization."""
    manager = XrayManager(temp_config)
    assert manager.config == temp_config
    assert manager.process is None
    assert manager.xray_config_file is None


def test_generate_xray_config(manager, temp_config):
    """Test Xray configuration generation."""
    server = {
        "id": "test",
        "name": "Test Server",
        "protocol": "vless",
        "address": "example.com",
        "port": 443,
        "uuid": "test-uuid-1234",
        "network": "tcp",
        "tls": "tls",
        "sni": "example.com",
    }

    config = manager._generate_xray_config(server)

    assert "log" in config
    assert "inbounds" in config
    assert "outbounds" in config
    assert len(config["inbounds"]) >= 1
    assert len(config["outbounds"]) >= 1

    # Check inbound
    inbound = config["inbounds"][0]
    assert inbound["protocol"] == "socks"
    assert inbound["port"] == 10808

    # Check outbound
    outbound = config["outbounds"][0]
    assert outbound["protocol"] == "vless"
    assert outbound["tag"] == "proxy"


def test_create_outbound_vless(manager):
    """Test VLESS outbound creation."""
    server = {
        "protocol": "vless",
        "address": "example.com",
        "port": 443,
        "uuid": "test-uuid",
        "network": "tcp",
    }

    outbound = manager._create_outbound(server)

    assert outbound["protocol"] == "vless"
    assert "vnext" in outbound["settings"]
    assert outbound["settings"]["vnext"][0]["address"] == "example.com"
    assert outbound["settings"]["vnext"][0]["port"] == 443


def test_create_outbound_vmess(manager):
    """Test VMess outbound creation."""
    server = {
        "protocol": "vmess",
        "address": "example.com",
        "port": 443,
        "uuid": "test-uuid",
        "alter_id": 0,
        "network": "tcp",
    }

    outbound = manager._create_outbound(server)

    assert outbound["protocol"] == "vmess"
    assert "vnext" in outbound["settings"]
    assert outbound["settings"]["vnext"][0]["users"][0]["id"] == "test-uuid"


def test_create_outbound_trojan(manager):
    """Test Trojan outbound creation."""
    server = {
        "protocol": "trojan",
        "address": "example.com",
        "port": 443,
        "password": "test-password",
        "network": "tcp",
    }

    outbound = manager._create_outbound(server)

    assert outbound["protocol"] == "trojan"
    assert "servers" in outbound["settings"]
    assert outbound["settings"]["servers"][0]["password"] == "test-password"


def test_create_stream_settings_tcp(manager):
    """Test TCP stream settings."""
    server = {"network": "tcp", "tls": "none"}
    settings = manager._create_stream_settings(server)

    assert settings["network"] == "tcp"
    assert settings["security"] == "none"


def test_create_stream_settings_ws(manager):
    """Test WebSocket stream settings."""
    server = {
        "network": "ws",
        "tls": "tls",
        "path": "/path",
        "sni": "example.com",
        "address": "example.com",
    }
    settings = manager._create_stream_settings(server)

    assert settings["network"] == "ws"
    assert settings["security"] == "tls"
    assert "wsSettings" in settings
    assert settings["wsSettings"]["path"] == "/path"


def test_is_running_no_process(manager):
    """Test is_running with no process."""
    assert manager.is_running() is False


def test_is_running_with_process(manager):
    """Test is_running with active process."""
    mock_process = Mock()
    mock_process.poll.return_value = None
    manager.process = mock_process

    assert manager.is_running() is True


def test_is_running_exited_process(manager):
    """Test is_running with exited process."""
    mock_process = Mock()
    mock_process.poll.return_value = 0
    manager.process = mock_process

    assert manager.is_running() is False
    assert manager.process is None


def test_get_status_not_running(manager):
    """Test get_status when not running."""
    status = manager.get_status()

    assert status["running"] is False
    assert status["pid"] is None
    assert status["config_file"] is None


def test_get_status_running(manager):
    """Test get_status when running."""
    mock_process = Mock()
    mock_process.pid = 12345
    mock_process.poll.return_value = None
    manager.process = mock_process
    manager.xray_config_file = Path("/tmp/test.json")

    status = manager.get_status()

    assert status["running"] is True
    assert status["pid"] == 12345
    assert status["config_file"] == "/tmp/test.json"
