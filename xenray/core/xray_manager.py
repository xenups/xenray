"""Xray process management for xenray."""

import json
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import psutil

from xenray.core.config import Config

logger = logging.getLogger(__name__)


class XrayManager:
    """Manages Xray process lifecycle."""

    def __init__(self, config: Config):
        """Initialize Xray manager.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.xray_config_file: Optional[Path] = None
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Setup logging configuration."""
        log_level = self.config.get("log_level", "info").upper()
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    def _find_xray_binary(self) -> Optional[Path]:
        """Find Xray binary.

        Returns:
            Path to Xray binary or None if not found
        """
        xray_binary = self.config.get("xray_binary")

        # Check if xray_binary is configured
        if not xray_binary:
            logger.warning("Xray binary path not configured")
            return None

        # Check if it's an absolute path
        if os.path.isabs(xray_binary):
            path = Path(xray_binary)
            if path.exists():
                return path

        # Check if it's in PATH
        found = shutil.which(xray_binary)
        if found:
            return Path(found)

        # Check common installation locations
        system = platform.system()
        common_paths = []

        if system == "Windows":
            common_paths = [
                Path("C:/Program Files/Xray/xray.exe"),
                Path("C:/Program Files (x86)/Xray/xray.exe"),
                Path.home() / "AppData" / "Local" / "Xray" / "xray.exe",
            ]
        elif system == "Darwin":
            common_paths = [
                Path("/usr/local/bin/xray"),
                Path("/opt/homebrew/bin/xray"),
                Path.home() / ".local" / "bin" / "xray",
            ]
        else:  # Linux
            common_paths = [
                Path("/usr/local/bin/xray"),
                Path("/usr/bin/xray"),
                Path.home() / ".local" / "bin" / "xray",
            ]

        for path in common_paths:
            if path.exists():
                return path

        logger.warning(f"Xray binary not found: {xray_binary}")
        return None

    def _generate_xray_config(self, server: Dict[str, Any]) -> Dict[str, Any]:
        """Generate Xray configuration from server settings.

        Args:
            server: Server configuration

        Returns:
            Xray configuration dictionary
        """
        inbound_config = self.config.get("inbound", {})

        xray_config = {
            "log": {"loglevel": self.config.get("log_level", "info")},
            "inbounds": [
                {
                    "tag": "socks-in",
                    "protocol": inbound_config.get("protocol", "socks"),
                    "listen": inbound_config.get("listen", "127.0.0.1"),
                    "port": inbound_config.get("port", 10808),
                    "settings": {"auth": "noauth", "udp": True},
                }
            ],
            "outbounds": [self._create_outbound(server), {"protocol": "freedom", "tag": "direct"}],
            "routing": {
                "domainStrategy": "AsIs",
                "rules": [{"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"}],
            },
        }

        return xray_config

    def _create_outbound(self, server: Dict[str, Any]) -> Dict[str, Any]:
        """Create outbound configuration for a server.

        Args:
            server: Server configuration

        Returns:
            Outbound configuration
        """
        protocol = server.get("protocol", "vless")
        outbound = {
            "tag": "proxy",
            "protocol": protocol,
            "settings": {},
            "streamSettings": self._create_stream_settings(server),
        }

        if protocol == "vless":
            outbound["settings"] = {
                "vnext": [
                    {
                        "address": server.get("address"),
                        "port": server.get("port"),
                        "users": [
                            {
                                "id": server.get("uuid"),
                                "encryption": server.get("encryption", "none"),
                                "flow": server.get("flow", ""),
                            }
                        ],
                    }
                ]
            }
        elif protocol == "vmess":
            outbound["settings"] = {
                "vnext": [
                    {
                        "address": server.get("address"),
                        "port": server.get("port"),
                        "users": [
                            {
                                "id": server.get("uuid"),
                                "alterId": server.get("alter_id", 0),
                                "security": server.get("security", "auto"),
                            }
                        ],
                    }
                ]
            }
        elif protocol == "trojan":
            outbound["settings"] = {
                "servers": [
                    {
                        "address": server.get("address"),
                        "port": server.get("port"),
                        "password": server.get("password"),
                    }
                ]
            }
        elif protocol == "shadowsocks":
            outbound["settings"] = {
                "servers": [
                    {
                        "address": server.get("address"),
                        "port": server.get("port"),
                        "method": server.get("method", "aes-256-gcm"),
                        "password": server.get("password"),
                    }
                ]
            }

        return outbound

    def _create_stream_settings(self, server: Dict[str, Any]) -> Dict[str, Any]:
        """Create stream settings for a server.

        Args:
            server: Server configuration

        Returns:
            Stream settings
        """
        network = server.get("network", "tcp")
        stream_settings = {
            "network": network,
            "security": server.get("tls", "none"),
        }

        if server.get("tls") == "tls":
            stream_settings["tlsSettings"] = {
                "serverName": server.get("sni", server.get("address")),
                "allowInsecure": server.get("allow_insecure", False),
            }

        if network == "ws":
            stream_settings["wsSettings"] = {
                "path": server.get("path", "/"),
                "headers": server.get("headers", {}),
            }
        elif network == "grpc":
            stream_settings["grpcSettings"] = {
                "serviceName": server.get("service_name", ""),
            }
        elif network == "h2":
            stream_settings["httpSettings"] = {
                "host": server.get("host", []),
                "path": server.get("path", "/"),
            }

        return stream_settings

    def start(self, server: Optional[Dict[str, Any]] = None) -> bool:
        """Start Xray process.

        Args:
            server: Server configuration. If None, uses active server from config.

        Returns:
            True if started successfully, False otherwise
        """
        if self.is_running():
            logger.warning("Xray is already running")
            return False

        # Get server configuration
        if server is None:
            server = self.config.get_active_server()
            if server is None:
                logger.error("No active server configured")
                return False

        # Find Xray binary
        xray_binary = self._find_xray_binary()
        if xray_binary is None:
            logger.error("Xray binary not found")
            return False

        # Generate Xray configuration
        xray_config = self._generate_xray_config(server)

        # Write configuration to temporary file
        config_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as f:
                json.dump(xray_config, f, indent=2)
                config_file = Path(f.name)

            # Start Xray process
            logger.info(f"Starting Xray with config: {config_file}")
            self.process = subprocess.Popen(
                [str(xray_binary), "run", "-c", str(config_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Wait a bit and check if process is still running
            time.sleep(1)
            if self.process.poll() is not None:
                # Process exited
                _, stderr = self.process.communicate()
                logger.error(f"Xray failed to start: {stderr}")
                # Clean up config file on failure
                if config_file and config_file.exists():
                    config_file.unlink()
                return False

            # Only set self.xray_config_file if successful
            self.xray_config_file = config_file
            logger.info(f"Xray started successfully (PID: {self.process.pid})")
            return True

        except Exception as e:
            logger.error(f"Failed to start Xray: {e}")
            # Clean up config file on exception
            if config_file and config_file.exists():
                try:
                    config_file.unlink()
                except Exception:
                    pass
            return False

    def stop(self) -> bool:
        """Stop Xray process.

        Returns:
            True if stopped successfully, False otherwise
        """
        if not self.is_running():
            logger.warning("Xray is not running")
            return False

        try:
            logger.info("Stopping Xray...")
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("Xray didn't terminate, killing...")
                    self.process.kill()
                    self.process.wait()

                self.process = None

            # Clean up config file
            if self.xray_config_file and self.xray_config_file.exists():
                self.xray_config_file.unlink()
                self.xray_config_file = None

            logger.info("Xray stopped successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to stop Xray: {e}")
            return False

    def restart(self, server: Optional[Dict[str, Any]] = None) -> bool:
        """Restart Xray process.

        Args:
            server: Server configuration. If None, uses active server.

        Returns:
            True if restarted successfully, False otherwise
        """
        self.stop()
        time.sleep(1)
        return self.start(server)

    def is_running(self) -> bool:
        """Check if Xray process is running.

        Returns:
            True if running, False otherwise
        """
        if self.process is None:
            return False

        if self.process.poll() is not None:
            # Process has exited
            self.process = None
            return False

        return True

    def get_status(self) -> Dict[str, Any]:
        """Get Xray process status.

        Returns:
            Status dictionary
        """
        status = {
            "running": self.is_running(),
            "pid": self.process.pid if self.process else None,
            "config_file": str(self.xray_config_file) if self.xray_config_file else None,
        }

        if self.is_running() and self.process:
            try:
                proc = psutil.Process(self.process.pid)
                status["cpu_percent"] = proc.cpu_percent(interval=0.1)
                status["memory_mb"] = proc.memory_info().rss / 1024 / 1024
                status["create_time"] = proc.create_time()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return status
