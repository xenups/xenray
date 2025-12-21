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
            self._main._config_manager,
            self._main._on_server_selected,
            on_profile_updated=self._main._on_profile_updated,
            toast_manager=self._main._toast,
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

        # Settings drawer
        self._main._settings_drawer = SettingsDrawer(
            self._main._config_manager,
            self._main._run_specific_installer,
            self._main._on_mode_changed,
            lambda: self._main._current_mode,
            navigate_to=self._main.navigate_to,
            navigate_back=self._main.navigate_back,
        )

        # Logs drawer
        self._main._logs_drawer_component = LogsDrawer(self._main._log_viewer, self._main._logs_heartbeat)

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
            enable_drag=True,
        )

        # Load last selected profile
        self._load_last_profile()

    def _load_last_profile(self):
        """Load and set the last selected profile."""
        last_profile_id = self._main._config_manager.get_last_selected_profile_id()
        if last_profile_id:
            profiles = self._main._config_manager.load_profiles()
            for profile in profiles:
                if profile.get("id") == last_profile_id:
                    self._main._selected_profile = profile
                    self._main._server_card.update_server(profile)
                    break

    def open_server_drawer(self, e=None):
        """Open the server list bottom sheet."""
        if self._main._server_sheet:
            self._main._page.open(self._main._server_sheet)
            self._safe_update_server_list()

    def open_logs_drawer(self, e=None):
        """Open the logs drawer."""
        if self._main._page.end_drawer != self._main._logs_drawer_component:
            self._main._page.end_drawer = self._main._logs_drawer_component
        self._main._logs_drawer_component.open = True
        self._main._page.update()
        # Trigger immediate stats update so user doesn't wait 1.5s for the first reading
        self._main._network_stats_handler.update_ui_immediately()

    def open_settings_drawer(self, e=None):
        """Open the settings drawer."""
        if self._main._page.end_drawer != self._main._settings_drawer:
            self._main._page.end_drawer = self._main._settings_drawer
        self._main._settings_drawer.open = True
        self._main._page.update()

    def _safe_update_server_list(self):
        """Wait for sheet to be mounted before updating list."""

        def _wait_and_update():
            max_wait = 2
            start = time.time()
            while time.time() - start < max_wait:
                if self._main._server_sheet and self._main._server_sheet.page:
                    try:
                        self._main._server_list._load_profiles(update_ui=True)
                    except Exception:
                        pass
                    break
                time.sleep(0.05)

        threading.Thread(target=_wait_and_update, daemon=True).start()
