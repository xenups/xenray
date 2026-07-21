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
        logger.debug("[TRAY] setup() called — binding MainWindow")
        self._main = main_window
        if not self._icon:
            self._init_tray()

    def _load_icon(self) -> Image.Image:
        """Load the application icon using Pillow."""
        icon_path = os.path.join(APPDIR, "assets", "icon.png")
        if not os.path.exists(icon_path):
            # Fallback to ico if png doesn't exist (though pystray handles PIL images best)
            icon_path = os.path.join(APPDIR, "assets", "icon.ico")

        try:
            return Image.open(icon_path)
        except Exception as e:
            logger.error(f"Failed to load tray icon: {e}")
            # Create a blank image as last resort
            return Image.new("RGBA", (64, 64), (0, 0, 0, 0))

    def _init_tray(self):
        """Initialize and start the tray icon."""
        logger.debug("[TRAY] _init_tray() — creating tray icon")
        if self._icon:
            logger.debug("[TRAY] _init_tray() — icon already exists, skipping")
            return

        self._icon = pystray.Icon(
            name="XenRay",
            icon=self._icon_image,
            title="XenRay",
            menu=self._create_menu(),
        )

        try:
            self._icon.run_detached()
            logger.debug("[TRAY] _init_tray() — run_detached() succeeded")
        except Exception as e:
            logger.warning(f"[TRAY] run_detached failed, falling back to thread: {e}")
            self._tray_thread = threading.Thread(target=self._icon.run, daemon=True)
            self._tray_thread.start()
            logger.debug("[TRAY] _init_tray() — tray thread started")

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
            self._icon.title = f"XenRay - {title}"

    def stop(self):
        """Shutdown the tray icon."""
        if self._icon:
            self._icon.stop()
            self._icon = None

    # --- Callbacks ---
    def _on_open(self, icon, item):
        """Restore window callback."""
        logger.debug("[TRAY_EVENT] _on_open() called")
        if not self._main:
            return
        self._main._restore_from_tray()

    def _on_toggle_connect(self, icon, item):
        """Toggle connection callback."""
        logger.debug("[TRAY_EVENT] _on_toggle_connect() called")
        try:
            self._main._on_connect_clicked(None)
        except Exception as e:
            logger.debug(f"[TRAY_EVENT] _on_toggle_connect error: {e}")

    def _on_exit(self, icon, item):
        """Final exit callback."""
        logger.debug("[TRAY_EVENT] _on_exit() called — user clicked Exit")
        try:
            icon.stop()
            from src.utils.process_utils import ProcessUtils

            try:
                self._main.cleanup()
            except Exception:
                pass

            ProcessUtils.kill_process_tree()
            os._exit(0)
        except Exception as e:
            logger.error(f"[TRAY_EVENT] Systray exit error: {e}")
            os._exit(1)
