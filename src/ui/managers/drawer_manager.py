"""Drawer Manager - Manages drawer initialization and opening."""
from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import flet as ft

from src.ui.components.logs_drawer import LogsDrawer
from src.ui.components.settings_drawer import SettingsDrawer
from src.ui.log_viewer import LogViewer
from src.ui.server_list import ServerList
from src.ui.helpers.ui_thread_helper import UIThreadHelper

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class DrawerManager:
    """Manages all drawers (server list, logs, settings)."""

    def __init__(self, main_window: MainWindow):
        self._main = main_window

    def setup_drawers(self):
        """Initialize all drawer components."""
        # Log viewer
        self._main._log_viewer = LogViewer("Connection Logs")
        self._main._log_viewer.set_page(self._main._page)

        # Server list
        self._main._server_list = ServerList(
            self._main._app_context,
            self._main._on_server_selected,
            on_profile_updated=self._main._on_profile_updated,
            toast_manager=self._main._toast,
            navigate_to=self._main.navigate_to,
            navigate_back=self._main.navigate_back,
            close_sheet=lambda: self._close_server_sheet(),
        )
        self._main._server_list.set_page(self._main._page)

        # Logs heartbeat indicator
        self._main._logs_heartbeat = ft.Container(
            width=12,
            height=12,
            bgcolor=ft.Colors.GREEN_400,
            border_radius=6,
            animate_opacity=800,
            animate_scale=ft.Animation(800, ft.AnimationCurve.EASE_IN_OUT),
            opacity=0.3,
            scale=1.0,
            shadow=ft.BoxShadow(
                spread_radius=2,
                blur_radius=8,
                color=ft.Colors.with_opacity(0.6, ft.Colors.GREEN_400),
            ),
        )

        # Settings drawer - set position in constructor for Flet 1.0
        self._main._settings_drawer = SettingsDrawer(
            self._main._app_context,
            self._main._run_specific_installer,
            self._main._on_mode_changed,
            lambda: self._main._current_mode,
            navigate_to=self._main.navigate_to,
            navigate_back=self._main.navigate_back,
        )
        self._main._settings_drawer.position = "end"

        # Logs drawer - set position in constructor for Flet 1.0
        self._main._logs_drawer_component = LogsDrawer(self._main._log_viewer, self._main._logs_heartbeat)
        self._main._logs_drawer_component.position = "end"

        # Server bottom sheet
        self._main._server_sheet = ft.BottomSheet(
            ft.Container(
                content=self._main._server_list,
                padding=ft.padding.only(top=20),
                expand=True,
            ),
            open=False,
            bgcolor=ft.Colors.TRANSPARENT,
            elevation=0,
            draggable=True,
        )

        # Load last selected profile
        self._load_last_profile()

        # Add bottom sheet to page overlay (BottomSheet does have open= property)
        self._main._page.overlay.append(self._main._server_sheet)
        self._main._page.update()

    def _load_last_profile(self):
        """Load and set the last selected profile."""
        last_profile_id = self._main._app_context.settings.get_last_selected_profile_id()
        if last_profile_id:
            profiles = self._main._app_context.profiles.load_all()
            for profile in profiles:
                if profile.get("id") == last_profile_id:
                    self._main._selected_profile = profile
                    self._main._server_card.update_server(profile)
                    break

    def _close_server_sheet(self):
        """Close the server list bottom sheet."""
        if self._main._server_sheet:
            self._main._server_sheet.open = False
            self._main._page.update()

    def open_server_drawer(self, e=None):
        """Open the server list bottom sheet."""
        if self._main._server_sheet:
            self._main._server_sheet.open = True
            self._main._page.update()
            self._safe_update_server_list()

    def open_logs_drawer(self, e=None):
        """Open the logs drawer."""
        # Use page.end_drawer and show_end_drawer() for Flet 0.80.0
        # show_end_drawer is async, so use run_task to await it
        self._main._page.end_drawer = self._main._logs_drawer_component
        self._main._logs_drawer_component.set_visible(True)  # Track visibility for performance
        self._main._page.run_task(self._main._page.show_end_drawer)
        # Trigger immediate stats update so user doesn't wait 1.5s for the first reading
        self._main._network_stats_handler.update_ui_immediately()

    def open_settings_drawer(self, e=None):
        """Open the settings drawer."""
        # Use page.end_drawer and show_end_drawer() for Flet 0.80.0
        # show_end_drawer is async, so use run_task to await it
        self._main._page.end_drawer = self._main._settings_drawer
        self._main._page.run_task(self._main._page.show_end_drawer)

    def _safe_update_server_list(self):
        """Wait for sheet to be mounted before updating list."""

        def _wait_and_update():
            max_wait = 2
            start = time.time()
            while time.time() - start < max_wait:
                if self._main._server_sheet and UIThreadHelper.is_mounted(self._main._server_sheet):
                    try:
                        self._main._server_list._load_profiles(update_ui=True)
                    except Exception:
                        pass
                    break
                time.sleep(0.05)

        threading.Thread(target=_wait_and_update, daemon=True).start()
