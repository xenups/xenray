"""Unified Dependency Manager."""
import os

from src.services.xray_installer import XrayInstallerService


class DependencyManager:
    """Manages installation of external dependencies."""
    
    @staticmethod
    def check_installed() -> list:
        """Return list of missing components."""
        missing = []
        if not XrayInstallerService.is_installed():
            missing.append("Xray Core")
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
        return True
