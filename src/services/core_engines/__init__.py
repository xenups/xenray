"""Core engines domain services (Xray and Sing-box engines)."""

from __future__ import annotations

from src.services.core_engines import config_utils
from src.services.core_engines.config_patcher import ConfigPatcher
from src.services.core_engines.config_utils import get_server_object, is_ip
from src.services.core_engines.legacy_config_service import LegacyConfigService
from src.services.core_engines.singbox_process_manager import SingboxProcessManager
from src.services.core_engines.singbox_service import SingboxService
from src.services.core_engines.xray_config_processor import XrayConfigProcessor
from src.services.core_engines.xray_process_manager import XrayProcessManager
from src.services.core_engines.xray_service import XrayService

__all__ = [
    "XrayService",
    "XrayProcessManager",
    "SingboxService",
    "SingboxProcessManager",
    "XrayConfigProcessor",
    "ConfigPatcher",
    "config_utils",
    "is_ip",
    "get_server_object",
    "LegacyConfigService",
]
