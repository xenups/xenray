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


def main(page: ft.Page):
    """Main entry point."""

    # Window Placement (Start Hidden)
    page.window.visible = False
    page.window.center()

    # Ensure tray icon matches app state (basic setup here, detailed in MainWindow)

    # Setup logging
    Settings.create_temp_directories()
    Settings.create_log_files()
    Settings.setup_logging(EARLY_LOG_FILE)

    # Initialize Core Services
    config_manager = ConfigManager()
    connection_manager = ConnectionManager(config_manager)
    
    # Initialize i18n with saved language
    from src.core.i18n import set_language
    saved_lang = config_manager.get_language()
    set_language(saved_lang)

    # Initialize UI
    window = MainWindow(page, config_manager, connection_manager)

    # Handle window close and minimize
    def on_window_event(e):
        logger.debug(f"[DEBUG] Window event: {e.data}")
        if e.data == "close":
            logger.debug("[DEBUG] Closing window...")
            try:
                # Cleanup resources
                window.cleanup()
                logger.debug("[DEBUG] Cleanup finished")
            except Exception as ex:
                logger.debug(f"[DEBUG] Cleanup error: {ex}")

            logger.debug("[DEBUG] Destroying window")
            page.window.destroy()
            logger.debug("[DEBUG] Window destroyed")
            # Force exit to ensure no hanging threads or zombie processes
            logger.info("[DEBUG] Killing process tree...")
            from src.utils.process_utils import ProcessUtils

            ProcessUtils.kill_process_tree()

            # Fallback
            os._exit(0)

    page.window.prevent_close = True
    page.window.on_event = on_window_event


def run():
    """Entry point for poetry script."""
    # Singleton Check (Moved here to prevent child processes from starting app)
    import ctypes

    # Import PlatformUtils with proper handling for PyInstaller
    import sys
    import os
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller executable
        app_dir = os.path.dirname(sys.executable)
        sys.path.insert(0, app_dir)
        sys.path.insert(0, os.path.join(app_dir, 'src'))
        # Import directly from the module file
        import importlib.util
        spec = importlib.util.spec_from_file_location("platform_utils", os.path.join(app_dir, "src", "utils", "platform_utils.py"))
        platform_utils = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(platform_utils)
        PlatformUtils = platform_utils.PlatformUtils
    else:
        # Running as script
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
        import os
        import fcntl
        import errno

        pid_file = os.path.expanduser("~/.xenray.pid")
        try:
            with open(pid_file, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                f.write(str(os.getpid()))
                global _pid_file_handle
                _pid_file_handle = f
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
    if getattr(sys, 'frozen', False):
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
