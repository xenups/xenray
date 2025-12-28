"""Main application entry point."""

import os
import sys

# Add project root to path
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

from src.core.constants import EARLY_LOG_FILE
from src.core.logger import logger
from src.core.settings import Settings


async def main(page):
    """Main entry point."""
    # Lazy-import Flet here (type hints available in function scope)

    logger.debug("[DEBUG] Starting Flet session (async main)")
    page.window.width = 420
    page.window.height = 550
    await page.window.center()
    page.title = "XenRay"
    page.window.prevent_close = True
    page.window.resizable = False
    page.window.minimizable = True
    page.window.maximizable = False
    # Don't update yet - keep window hidden

    # Setup logging
    Settings.create_temp_directories()
    Settings.create_log_files()
    Settings.setup_logging(EARLY_LOG_FILE)

    # Initialize DI Container
    from src.core.container import ApplicationContainer

    container = ApplicationContainer()

    # Initialize i18n
    from src.core.i18n import set_language

    set_language(container.app_context().settings.get_language())

    # Initialize UI with DI
    window = container.main_window(page=page)

    # Register window event handler
    def on_window_event(e):
        logger.debug(f"[DEBUG] Window event in main.py: {e.data}")
        if e.data == "close":
            logger.debug("[DEBUG] Close event detected, calling show_close_dialog")
            window.show_close_dialog()
            # Explicit update to ensure dialog renders before any potential default hide
            page.update()

    page.window.on_event = on_window_event

    # NOW show the window - it already has correct size so no flash
    page.window.visible = True
    await page.update_async() if hasattr(page, "update_async") else page.update()

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
    """Entry point for poetry script - routes to GUI or CLI."""
    import os  # Import early for getcwd and env vars

    # Import logger early so it's available for both modes
    from src.core.logger import logger

    # Log early startup info for debugging Windows boot issues
    logger.info(f"[Startup] XenRay starting, argv={sys.argv}, cwd={os.getcwd()}")

    # Check if CLI mode is requested (any command-line arguments)
    if len(sys.argv) > 1:
        # CLI mode - delegate to CLI handler (no Flet import!)

        os.environ["XENRAY_SKIP_I18N"] = "1"

        from src.cli import main as cli_main

        cli_main()
        return

    # GUI mode - continue with normal GUI startup
    # Lazy-import Flet here (only when GUI is actually needed)
    # This defers 115MB of framework overhead until this point
    # Singleton Check (Moved here to prevent child processes from starting app)
    import ctypes
    import os

    import flet as ft

    # Import PlatformUtils - works for both script and PyInstaller
    # PyInstaller bundles these as hidden-imports
    from src.utils.platform_utils import PlatformUtils

    # Platform-specific singleton check
    if PlatformUtils.get_platform() == "windows":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        mutex_name = "Global\\XenRay_Singleton_Mutex_v1"

        # CRITICAL: Clear last error before creating mutex to avoid false positives
        ctypes.set_last_error(0)

        # Create named mutex (Keep reference to prevent GC)
        global _singleton_mutex
        _singleton_mutex = kernel32.CreateMutexW(None, False, mutex_name)

        # Get the error AFTER creating the mutex
        last_error = ctypes.get_last_error()
        logger.debug(f"[Startup] Mutex creation result: handle={_singleton_mutex}, last_error={last_error}")

        if last_error == 183:  # ERROR_ALREADY_EXISTS
            # Application is already running
            logger.warning("Another instance is already running. Exiting.")
            return  # Exit run() without starting app
        elif _singleton_mutex == 0:
            # Mutex creation failed entirely
            logger.error(f"[Startup] Failed to create mutex, error code: {last_error}")
            # Continue anyway - better to have multiple instances than no app
        else:
            # Mutex created successfully, we'll keep it held
            pass
    else:
        # For Unix-like systems (macOS, Linux), we can use a PID file
        import errno
        import fcntl

        pid_file = os.path.expanduser("~/.xenray.pid")
        try:
            global _pid_file_handle
            _pid_file_handle = open(pid_file, "w")
            fcntl.flock(_pid_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _pid_file_handle.write(str(os.getpid()))
        except (IOError, OSError) as e:
            if e.errno == errno.EAGAIN:
                # Application is already running
                logger.warning("Another instance is already running. Exiting.")
                return
            else:
                raise

    # Calculate absolute path to assets directory using PlatformUtils
    # This handles both script development and frozen executable environments
    root_dir = PlatformUtils.get_app_dir()
    assets_path = os.path.join(root_dir, "assets")
    logger.debug(f"Assets path: {assets_path}")

    # Start with hidden window to prevent flash
    ft.app(
        target=main,
        assets_dir=assets_path,
        view=ft.AppView.FLET_APP_HIDDEN,
    )


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    run()
