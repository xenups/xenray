"""Protocol link parsers package."""

from __future__ import annotations

from src.core.parsers.base import (
    DEFAULT_ENCRYPTION,
    DEFAULT_FINGERPRINT,
    DEFAULT_NETWORK,
    DEFAULT_PATH,
    DEFAULT_PORT,
    DEFAULT_SECURITY,
    UUID_PATTERN,
    VALID_ENCRYPTION,
    VALID_NETWORKS,
    VALID_SECURITY,
    build_minimal_config,
)
from src.core.parsers.hysteria2 import Hysteria2Parser
from src.core.parsers.trojan import TrojanParser
from src.core.parsers.vless import VlessParser
from src.core.parsers.vmess import VmessParser

__all__ = [
    "VlessParser",
    "VmessParser",
    "TrojanParser",
    "Hysteria2Parser",
    "DEFAULT_PORT",
    "DEFAULT_NETWORK",
    "DEFAULT_PATH",
    "DEFAULT_ENCRYPTION",
    "DEFAULT_SECURITY",
    "DEFAULT_FINGERPRINT",
    "VALID_NETWORKS",
    "VALID_SECURITY",
    "VALID_ENCRYPTION",
    "UUID_PATTERN",
    "build_minimal_config",
]
