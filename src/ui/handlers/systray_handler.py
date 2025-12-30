"""System Tray Handler - Manages the tray icon and context menu."""
from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Optional

import pystray
from PIL import Image

from src.core.constants import APPDIR
from src.core.i18n import t
from src.core.logger import logger
from src.utils.platform_utils import Platform, PlatformUtils

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


from src.core.app_context import AppContext
from src.core.connection_manager import ConnectionManager


class SystrayHandler:
    """Handles the system tray icon and lifecycle."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        app_context: AppContext,
    ):
        self._connection_manager = connection_manager
        self._app_context = app_context
        self._main: Optional[MainWindow] = None
        self._icon: Optional[pystray.Icon] = None
        self._tray_thread: Optional[threading.Thread] = None

        # Load icon image
        self._icon_image = self._load_icon()

    def setup(self, main_window: MainWindow):
        """Bind main window to the handler and initialize tray."""
        self._main = main_window
        if not self._icon:
            self._init_tray()

    def _load_icon(self) -> Image.Image:
        """Load the application icon using Pillow."""
        icon_path = os.path.join(APPDIR, "assets", "icon.png")
        if not os.path.exists(icon_path):
            # Fallback to ico if png doesn't exist
            icon_path = os.path.join(APPDIR, "assets", "icon.ico")

        try:
            logger.debug(f"[Systray] Loading icon from: {icon_path}")
            img = Image.open(icon_path)
            
            # On Linux, ensure the icon is in RGBA mode and properly sized
            # Some Linux desktop environments require specific icon formats
            if PlatformUtils.get_platform() == Platform.LINUX:
                # Convert to RGBA if needed
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                
                # Resize to a standard tray icon size (22x22 or 24x24 is common)
                # Some Linux DEs may not display large icons correctly
                img = img.resize((48, 48), Image.Resampling.LANCZOS)
                logger.debug(f"[Systray] Linux icon: mode={img.mode}, size={img.size}")
            
            return img
        except Exception as e:
            logger.error(f"Failed to load tray icon: {e}")
            # Create a visible fallback icon (purple square) instead of transparent
            fallback = Image.new("RGBA", (48, 48), (128, 58, 237, 255))  # Purple
            return fallback

    def _init_tray(self):
        """Initialize and start the tray icon."""
        if self._icon:
            return

        logger.debug(f"[Systray] Initializing tray icon on {PlatformUtils.get_platform()}")
        
        self._icon = pystray.Icon(
            name="XenRay",
            icon=self._icon_image,
            title="XenRay",
            menu=self._create_menu(),
        )

        # Start tray in a separate thread or detached
        try:
            self._icon.run_detached()
            logger.debug("[Systray] Icon running in detached mode")
        except Exception as e:
            logger.warning(f"run_detached failed, falling back to thread: {e}")
            self._tray_thread = threading.Thread(target=self._icon.run, daemon=True)
            self._tray_thread.start()
            logger.debug("[Systray] Icon running in threaded mode")

    def _create_menu(self) -> pystray.Menu:
        """Create the tray context menu."""
        # Get labels based on current connection state
        if self._main._is_running:
            toggle_label = t("tray.disconnect")
            status_text = t("tray.connected_to").format(
                server=self._main._selected_profile.get("name", "Unknown") if self._main._selected_profile else "..."
            )
        else:
            toggle_label = t("tray.connect")
            status_text = t("app.disconnected")

        self.update_title(status_text)

        menu_items = [
            pystray.MenuItem(t("tray.open"), self._on_open, default=True),
            pystray.MenuItem(toggle_label, self._on_toggle_connect),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("tray.exit"), self._on_exit),
        ]
        return pystray.Menu(*menu_items)

    def update_state(self):
        """Update the menu and title when connection state changes."""
        if not self._icon:
            return

        # Refresh the menu to update Connect/Disconnect labels
        self._icon.menu = self._create_menu()

    def update_title(self, title: str):
        """Update the hover tooltip."""
        if self._icon:
            # Sanitize title for pystray compatibility on Linux
            # pystray on Linux (using GTK/AppIndicator) may fail with non-ASCII chars
            try:
                # Try to encode as latin-1, replacing problematic chars
                safe_title = title.encode("latin-1", errors="replace").decode("latin-1")
            except (UnicodeEncodeError, UnicodeDecodeError):
                safe_title = title.encode("ascii", errors="replace").decode("ascii")
            self._icon.title = f"XenRay - {safe_title}"

    def stop(self):
        """Shutdown the tray icon."""
        if self._icon:
            try:
                # On Linux, pystray can hang during stop, so do it in a
                # non-blocking way with a timeout
                if PlatformUtils.get_platform() == Platform.LINUX:
                    def _stop_icon():
                        try:
                            self._icon.stop()
                        except Exception:
                            pass
                    
                    stop_thread = threading.Thread(target=_stop_icon, daemon=True)
                    stop_thread.start()
                    stop_thread.join(timeout=1.0)  # Wait max 1 second
                    if stop_thread.is_alive():
                        logger.debug("[Systray] Icon stop timed out, continuing anyway")
                else:
                    self._icon.stop()
            except Exception as e:
                logger.debug(f"[Systray] Stop error (ignoring): {e}")
            finally:
                self._icon = None

    # --- Callbacks ---
    def _on_open(self, icon, item):
        """Restore window callback."""

        def _show():
            try:
                self._main._page.window.visible = True
                self._main._page.window.skip_task_bar = False
                self._main._page.window.to_front()
                self._main._page.update()
            except Exception as e:
                logger.debug(f"Systray restore error: {e}")

        try:
            self._main._ui_helper.call(_show)
        except Exception as e:
            logger.debug(f"Systray _on_open error: {e}")

    def _on_toggle_connect(self, icon, item):
        """Toggle connection callback."""
        try:
            # We need to run this on the UI thread or a safe thread
            self._main._on_connect_clicked(None)
        except Exception as e:
            logger.debug(f"Systray _on_toggle_connect error: {e}")

    def _on_exit(self, icon, item):
        """Final exit callback."""
        try:
            # Stop icon first (non-blocking on Linux)
            try:
                icon.stop()
            except Exception:
                pass

            # We use the MainWindow's cleanup or call ProcessUtils
            from src.utils.process_utils import ProcessUtils

            try:
                # First try graceful cleanup
                self._main.cleanup()
            except Exception:
                pass

            ProcessUtils.kill_process_tree()
            os._exit(0)
        except Exception as e:
            logger.error(f"Systray exit error: {e}")
            os._exit(1)
