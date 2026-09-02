"""Window Lifecycle Handler - manages close confirmation dialogs, tray minimization/restore, and app cleanup."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from src.core.constants import WINDOW_HEIGHT, WINDOW_WIDTH
from src.core.logger import logger
from src.ui.components.common.close_dialog import CloseDialog
from src.utils.process_utils import ProcessUtils

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class WindowLifecycleHandler:
    """Handler managing window events, tray minimization, restore, and cleanup."""

    def __init__(self, main_window: MainWindow) -> None:
        self._mw = main_window

    def show_close_dialog(self) -> None:
        """Show the close confirmation dialog."""
        logger.debug("[DEBUG] WindowLifecycleHandler.show_close_dialog() called")
        dialog = CloseDialog(
            on_exit=self._on_close_dialog_exit,
            on_minimize=self.minimize_to_tray,
            app_context=self._mw._app_context,
        )
        self._mw._page.show_dialog(dialog)

    def _on_close_dialog_exit(self) -> None:
        """Exit handler — triggers clean shutdown."""
        self.cleanup()
        from src.main import signal_exit

        signal_exit()
        ProcessUtils.kill_process_tree()
        os._exit(0)

    def minimize_to_tray(self) -> None:
        """Hide window to tray."""
        self._mw._page.window.visible = False
        self._mw._page.update()

    def restore_from_tray(self) -> None:
        """Restore window from tray — re-locks dimensions, then reveals."""

        async def _show() -> None:
            try:
                page = self._mw._page
                page.window.width = WINDOW_WIDTH
                page.window.height = WINDOW_HEIGHT
                page.window.min_width = 620
                page.window.min_height = 480
                page.window.max_width = 620
                page.window.max_height = 480
                page.window.resizable = False
                page.window.maximizable = False
                page.window.visible = True
                page.window.minimized = False
                page.update()
                await page.window.to_front()
            except Exception as e:
                logger.debug(f"[WindowLifecycleHandler] Restore error: {e}")

        self._mw._page.run_task(_show)

    def cleanup(self) -> None:
        """Cleanup system resources before exit."""
        logger.info("[WindowLifecycleHandler] Cleaning up MainWindow resources...")
        try:
            self._mw._network_stats.stop()
        except Exception:
            pass
        try:
            self._mw._connection_manager.cleanup()
        except Exception:
            pass
        try:
            self._mw._systray.stop()
        except Exception:
            pass
        try:
            self._mw._reconnect_event_handler.cleanup()
        except Exception:
            pass
        for view_name in (
            "_stitch_dashboard_view",
            "_stitch_statistics_view",
            "_lan_sharing_view",
        ):
            view = getattr(self._mw, view_name, None)
            if view is not None and hasattr(view, "dispose"):
                try:
                    view.dispose()
                except Exception:
                    pass

        lan_row = getattr(getattr(self._mw, "_settings_drawer", None), "_lan_share_row", None)
        if lan_row is not None and hasattr(lan_row, "dispose"):
            try:
                lan_row.dispose()
            except Exception:
                pass
        try:
            from src.utils.firewall_manager import FirewallManager

            FirewallManager.remove_lan_firewall_rule()
        except Exception:
            pass
