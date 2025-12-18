"""Main application entry point."""

import os
import sys

import flet as ft

# Add project root to path
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config_manager import ConfigManager
from src.core.connection_manager import ConnectionManager
from src.core.constants import EARLY_LOG_FILE
from src.core.logger import logger
from src.core.settings import Settings
from src.ui.main_window import MainWindow


import asyncio

async def main(page: ft.Page):
    """Main entry point."""
    logger.debug("[DEBUG] Starting Flet session (async main)")
    
    # Window settings MUST be set as early as possible
    page.window.prevent_close = True
    page.title = "XenRay"
    page.window.width = 420
    page.window.height = 550
    page.window.resizable = False
    page.window.center()
    page.update()

    # Setup logging
    Settings.create_temp_directories()
    Settings.create_log_files()
    Settings.setup_logging(EARLY_LOG_FILE)

    # Initialize Core Services
    config_manager = ConfigManager()
    connection_manager = ConnectionManager(config_manager)

    # Initialize i18n
    from src.core.i18n import set_language
    set_language(config_manager.get_language())

    # Initialize UI
    window = MainWindow(page, config_manager, connection_manager)

    # Register window event handler
    def on_window_event(e):
        logger.debug(f"[DEBUG] Window event in main.py: {e.data}")
        if e.data == "close":
            logger.debug("[DEBUG] Close event detected, calling show_close_dialog")
            window.show_close_dialog()
            # Explicit update to ensure dialog renders before any potential default hide
            page.update()

    page.window.on_event = on_window_event
    page.update()

    # Keep session alive - use a larger sleep to reduce overhead
    logger.debug("[DEBUG] Session initialized, entering persistence loop")
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.debug("[DEBUG] Flet session task cancelled")
    except Exception as e:
        logger.error(f"[ERROR] Main persistence loop crashed: {e}")


def run():
    """Entry point for poetry script."""
    # Singleton Check (Moved here to prevent child processes from starting app)
    import ctypes
    import sys
    import os

    # Import PlatformUtils - works for both script and PyInstaller
    # PyInstaller bundles these as hidden-imports
    from src.utils.platform_utils import PlatformUtils

    # Platform-specific singleton check
    if PlatformUtils.get_platform() == "windows":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        mutex_name = "Global\\XenRay_Singleton_Mutex_v1"

        # Create named mutex (Keep reference to prevent GC)
        global _singleton_mutex
        _singleton_mutex = kernel32.CreateMutexW(None, False, mutex_name)

        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            # Application is already running
            logger.warning("Another instance is already running. Exiting.")
            return  # Exit run() without starting app
    else:
        # For Unix-like systems (macOS, Linux), we can use a PID file
        import fcntl
        import errno

        pid_file = os.path.expanduser("~/.xenray.pid")
        try:
            global _pid_file_handle
            _pid_file_handle = open(pid_file, 'w')
            fcntl.flock(_pid_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _pid_file_handle.write(str(os.getpid()))
        except (IOError, OSError) as e:
            if e.errno == errno.EAGAIN:
                # Application is already running
                logger.warning("Another instance is already running. Exiting.")
                return
            else:
                raise

    # Calculate absolute path to assets directory
    # For PyInstaller frozen exe, use the exe's directory
    # For normal Python run, use the source directory
    if getattr(sys, "frozen", False):
        # Running as compiled exe - assets are next to the exe
        root_dir = os.path.dirname(sys.executable)
    else:
        # Running as script - assets are in project root
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    assets_path = os.path.join(root_dir, "assets")
    logger.debug(f"Assets path: {assets_path}")

    ft.app(target=main, assets_dir=assets_path)


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    run()
