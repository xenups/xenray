"""Installer and update domain services."""

from __future__ import annotations

from src.services.installer.app_update_service import AppUpdateService
from src.services.installer.archive_extractor import ArchiveExtractor, CorePermissionError
from src.services.installer.file_downloader import FileDownloader
from src.services.installer.rule_update_service import RuleUpdateService
from src.services.installer.singbox_installer import SingboxInstallerService
from src.services.installer.singbox_version_checker import SingboxVersionChecker
from src.services.installer.xray_installer import XrayInstallerService
from src.services.installer.xray_version_checker import XrayVersionChecker

__all__ = [
    "XrayInstallerService",
    "SingboxInstallerService",
    "FileDownloader",
    "ArchiveExtractor",
    "CorePermissionError",
    "XrayVersionChecker",
    "SingboxVersionChecker",
    "AppUpdateService",
    "RuleUpdateService",
]
