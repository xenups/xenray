"""Unified Dependency Manager."""
import os
import threading

from src.services.tun2proxy_installer import Tun2ProxyInstallerService
from src.services.xray_installer import XrayInstallerService


class DependencyManager:
    """Manages installation of external dependencies."""
    
    @staticmethod
    def check_installed() -> list:
        """Return list of missing components."""
        missing = []
        if not XrayInstallerService.is_installed():
            missing.append("Xray Core")
        if not Tun2ProxyInstallerService.is_installed():
            missing.append("Tun2Proxy")
        return missing

    @staticmethod
    def install_all(progress_callback=None) -> bool:
        """
        Install all missing dependencies.
        DEPRECATED: Now we only return True to bypass auto-install.
        User must manually update via Tools menu.
        """
        # We no longer auto-install on startup.
        # Just return True to allow app to proceed.
        # The UI will show missing components if they are not found, 
        # but we won't force install here.
        return True
