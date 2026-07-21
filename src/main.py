"""Main application entry point."""

import os
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

from src.core.constants import EARLY_LOG_FILE, WINDOW_HEIGHT, WINDOW_WIDTH
from src.core.logger import logger
from src.core.settings import Settings
from src.ui.theme import AppColors

_shutdown_event = asyncio.Event()


def signal_exit():
    _shutdown_event.set()


async def main(page):
    """Main entry point."""
    logger.debug("[DEBUG] Starting Flet session (async main)")

    # 1. Clear any leftover controls (safe on first call too)
    page.controls.clear()

    # 2. Lock native window dimensions at the very beginning
    page.window_width = WINDOW_WIDTH
    page.window_height = WINDOW_HEIGHT
    page.window_min_width = WINDOW_WIDTH
    page.window_min_height = WINDOW_HEIGHT
    page.window_max_width = WINDOW_WIDTH
    page.window_max_height = WINDOW_HEIGHT
    page.window_resizable = False
    page.window.width = WINDOW_WIDTH
    page.window.height = WINDOW_HEIGHT
    page.window.min_width = WINDOW_WIDTH
    page.window.min_height = WINDOW_HEIGHT
    page.window.max_width = WINDOW_WIDTH
    page.window.max_height = WINDOW_HEIGHT
    page.window.resizable = False

    page.window.minimizable = True
    page.window.maximizable = False
    page.window.prevent_close = True
    page.title = "XenRay"
    page.padding = 0
    page.spacing = 0
    page.bgcolor = AppColors.GLASS_OVERLAY

    # 3. Background initialization
    Settings.create_temp_directories()
    Settings.create_log_files()
    Settings.setup_logging(EARLY_LOG_FILE)

    from src.core.container import ApplicationContainer

    container = ApplicationContainer()

    from src.core.i18n import set_language

    set_language(container.app_context().settings.get_language())

    # 5. Build UI — first page.update() flushes dimensions + center + content in one frame
    window = container.main_window(page=page)
    page.add(window._stack)

    # 6. Window event handler — checks both e.data and e.type
    async def on_window_event(e):
        event_type_str = str(getattr(e, "type", "")).lower()
        event_data_str = str(e.data).lower() if e.data is not None else ""
        logger.debug(f"[WINDOW_EVENT] data='{e.data}' type='{getattr(e, 'type', None)}'")

        is_close = "close" in event_type_str or "close" in event_data_str
        is_minimize = "minimize" in event_type_str or "minimize" in event_data_str

        if is_close:
            if window._app_context.settings.get_remember_close_choice():
                logger.debug("[WINDOW_EVENT] Close + Always minimize — hiding to tray")
                page.window.visible = False
                page.update()
            else:
                logger.debug("[WINDOW_EVENT] Close matched — showing dialog")
                window.show_close_dialog()
                page.update()

        elif is_minimize:
            logger.debug("[WINDOW_EVENT] Minimize matched — hiding to tray")
            page.window.visible = False
            page.update()

        else:
            logger.debug("[WINDOW_EVENT] Ignored — no match")

    page.window.on_event = on_window_event

    # 7. Final sync — center, reveal, bring to front
    if hasattr(page.window, "center"):
        fn = page.window.center
        if asyncio.iscoroutinefunction(fn):
            await fn()
        else:
            fn()

    page.window.minimized = False
    page.window.visible = True
    page.update()

    if hasattr(page.window, "to_front"):
        fn = page.window.to_front
        if asyncio.iscoroutinefunction(fn):
            await fn()
        else:
            fn()

    # 8. Keep session alive until explicit shutdown
    logger.debug("[DEBUG] Session initialized, entering persistence loop")
    await _shutdown_event.wait()
    logger.debug("[DEBUG] Shutdown event received — exiting main()")


async def terminate_app(page):
    """Clean termination from close dialog or systray Exit."""
    logger.debug("[DEBUG] Terminating app")
    signal_exit()
    page.window.prevent_close = False
    page.update()
    await page.window.destroy()


def run():
    """Entry point for poetry script - routes to GUI or CLI."""
    import os

    from src.core.logger import logger

    logger.info(f"[Startup] XenRay starting, argv={sys.argv}, cwd={os.getcwd()}")

    if len(sys.argv) > 1:
        os.environ["XENRAY_SKIP_I18N"] = "1"
        from src.cli import main as cli_main

        cli_main()
        return

    import ctypes
    import os

    import flet as ft

    from src.utils.platform_utils import PlatformUtils

    if PlatformUtils.get_platform() == "windows":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        mutex_name = "Global\\XenRay_Singleton_Mutex_v1"
        ctypes.set_last_error(0)
        global _singleton_mutex
        _singleton_mutex = kernel32.CreateMutexW(None, False, mutex_name)
        last_error = ctypes.get_last_error()
        logger.debug(f"[Startup] Mutex creation result: handle={_singleton_mutex}, last_error={last_error}")
        if last_error == 183:
            logger.warning("Another instance is already running. Exiting.")
            return
        elif _singleton_mutex == 0:
            logger.error(f"[Startup] Failed to create mutex, error code: {last_error}")
    else:
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
                logger.warning("Another instance is already running. Exiting.")
                return
            else:
                raise

    root_dir = PlatformUtils.get_app_dir()
    assets_path = os.path.join(root_dir, "assets")
    logger.debug(f"Assets path: {assets_path}")

    ft.run(
        main,
        assets_dir=assets_path,
    )


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    run()
