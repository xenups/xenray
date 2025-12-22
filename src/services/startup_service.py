"""Startup Service - Manages automatic application launch on system startup.

This module handles platform-specific startup entry management.
It is UI-agnostic and acts as the single source of truth for startup state.
"""

import sys
from typing import Optional

from loguru import logger

from src.utils.platform_utils import PlatformUtils


class StartupService:
    """Service to manage application startup registration."""

    APP_NAME = "XenRay"
    REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

    @staticmethod
    def _get_launch_command() -> str:
        """
        Get the correct launch command for the current execution mode.

        Returns:
            Properly quoted command string for launching the application.
        """
        if PlatformUtils.is_frozen():
            # Frozen (PyInstaller) mode: use sys.executable directly
            executable = sys.executable
            return f'"{executable}"'
        else:
            # Script mode: python.exe + main.py
            import os

            python_exe = sys.executable
            # Navigate from src/services/startup_service.py to main.py
            current_file = os.path.abspath(__file__)
            services_dir = os.path.dirname(current_file)
            src_dir = os.path.dirname(services_dir)
            project_root = os.path.dirname(src_dir)
            main_py = os.path.join(project_root, "src", "main.py")

            return f'"{python_exe}" "{main_py}"'

    @staticmethod
    def is_supported() -> bool:
        """Check if startup management is supported on the current platform."""
        return PlatformUtils.get_platform() == "windows"

    @staticmethod
    def is_enabled() -> bool:
        """
        Check if application is registered to start on login.

        Returns True only if:
        - Registry key exists
        - Stored path matches the current resolved executable command

        Returns:
            True if startup is enabled and path is valid, False otherwise.
        """
        if not StartupService.is_supported():
            return False

        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                StartupService.REGISTRY_PATH,
                0,
                winreg.KEY_READ,
            )

            try:
                value, _ = winreg.QueryValueEx(key, StartupService.APP_NAME)
                winreg.CloseKey(key)

                # Verify the stored path matches current executable
                current_command = StartupService._get_launch_command()

                # Normalize paths for comparison (case-insensitive on Windows)
                return value.lower() == current_command.lower()

            except FileNotFoundError:
                # Key doesn't exist
                winreg.CloseKey(key)
                return False

        except Exception as e:
            logger.debug(f"[StartupService] Error checking startup status: {e}")
            return False

    @staticmethod
    def enable() -> bool:
        """
        Register application to start on login.

        Creates or updates the registry value with the resolved absolute launch command.

        Returns:
            True if successful, False otherwise.
        """
        if not StartupService.is_supported():
            logger.warning("[StartupService] Startup not supported on this platform")
            return False

        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                StartupService.REGISTRY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            )

            launch_command = StartupService._get_launch_command()
            winreg.SetValueEx(key, StartupService.APP_NAME, 0, winreg.REG_SZ, launch_command)
            winreg.CloseKey(key)

            logger.info(f"[StartupService] Enabled startup: {launch_command}")
            return True

        except Exception as e:
            logger.error(f"[StartupService] Failed to enable startup: {e}")
            return False

    @staticmethod
    def disable() -> bool:
        """
        Remove application from startup.

        Completely removes the registry key. Does NOT leave empty or invalid values.

        Returns:
            True if successful (or key didn't exist), False on error.
        """
        if not StartupService.is_supported():
            logger.warning("[StartupService] Startup not supported on this platform")
            return False

        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                StartupService.REGISTRY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            )

            try:
                winreg.DeleteValue(key, StartupService.APP_NAME)
                logger.info("[StartupService] Disabled startup")
            except FileNotFoundError:
                # Key doesn't exist, that's fine
                logger.debug("[StartupService] Startup key was not present")

            winreg.CloseKey(key)
            return True

        except Exception as e:
            logger.error(f"[StartupService] Failed to disable startup: {e}")
            return False

    @staticmethod
    def sync_state(config_enabled: bool) -> bool:
        """
        Sync startup state with configuration.

        If config says enabled but registry doesn't match (e.g., app moved),
        this will attempt to re-enable with the correct path.

        Args:
            config_enabled: The stored configuration preference.

        Returns:
            The actual current state after sync.
        """
        if not StartupService.is_supported():
            return False

        current_state = StartupService.is_enabled()

        if config_enabled and not current_state:
            # Config says enabled but registry is wrong/missing - re-enable
            StartupService.enable()
            return StartupService.is_enabled()

        return current_state
