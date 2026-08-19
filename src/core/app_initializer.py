import os
import sys

import flet as ft

from src.core.constants import EARLY_LOG_FILE, WINDOW_HEIGHT, WINDOW_WIDTH
from src.core.settings import Settings
from src.platform.factory import get_process_adapter
from src.ui.theme import AppColors


class AppInitializer:
    """Handles OS-level process grouping, window geometry setup, and logging startup."""

    @staticmethod
    def setup_windows_process_grouping() -> None:
        """Register AppUserModelID and process flags for OS process grouping."""
        get_process_adapter().initialize_environment()

    @staticmethod
    def get_absolute_icon_path() -> str:
        """Returns absolute path to assets/icon.ico for dev and PyInstaller execution."""
        if hasattr(sys, "_MEIPASS"):
            base_path = sys._MEIPASS
        else:
            # Go up from src/core/app_initializer.py to project root
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        icon_path = os.path.join(base_path, "assets", "icon.ico")
        return os.path.abspath(icon_path)

    @classmethod
    def configure_window_properties(cls, page: ft.Page) -> None:
        """Configure page and native OS window geometry properties per Flet 0.86+ specifications."""
        icon_path = cls.get_absolute_icon_path()

        page.window.title = "XenRay"
        if os.path.exists(icon_path):
            page.window.icon = icon_path

        page.window.width = WINDOW_WIDTH
        page.window.height = WINDOW_HEIGHT
        page.window.min_width = 620
        page.window.min_height = 480
        page.window.max_width = 620
        page.window.max_height = 480
        page.window.resizable = False
        page.window.minimizable = True
        page.window.maximizable = False
        page.window.prevent_close = True
        page.window.title_bar_hidden = True
        page.window.title_bar_buttons_hidden = True
        page.title = "XenRay"
        page.padding = 0
        page.spacing = 0
        page.bgcolor = AppColors.GLASS_OVERLAY
        page.update()

    @staticmethod
    def initialize_filesystem_and_logging() -> None:
        """Create temporary directories, log files, and early logger setup."""
        Settings.create_temp_directories()
        Settings.create_log_files()
        Settings.setup_logging(EARLY_LOG_FILE)
