"""Xenray - A modern, lightweight Xray client for Windows and Linux/macOS."""

__version__ = "0.1.0"
__author__ = "xenray contributors"
__description__ = "A modern, lightweight Xray client focusing on simplicity"

from xenray.core.config import Config
from xenray.core.xray_manager import XrayManager

__all__ = ["Config", "XrayManager", "__version__"]
