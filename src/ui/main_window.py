from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Optional, Callable

import flet as ft

# Local modules
from src.core.config_manager import ConfigManager
from src.core.connection_manager import ConnectionManager
from src.core.constants import TMPDIR, TUN_LOG_FILE, XRAY_LOG_FILE, APPDIR
from src.core.logger import logger
from src.core.types import ConnectionMode
from src.ui.components.connection_button import ConnectionButton
from src.ui.components.logs_drawer import LogsDrawer
from src.ui.components.server_card import ServerCard
from src.ui.components.settings_drawer import SettingsDrawer
from src.ui.components.status_display import StatusDisplay
from src.ui.components.header import Header
from src.ui.components.app_container import AppContainer
from src.ui.components.splash_overlay import SplashOverlay
from src.ui.log_viewer import LogViewer


class MainWindow:
    """Main Flet window for XenRay application."""

    def __init__(
        self,
        page: ft.Page,
        config_manager: ConfigManager,
        connection_manager: ConnectionManager,
    ):
        self._page = page
        self._config_manager = config_manager
        self._connection_manager = connection_manager

        # --- State Variables ---
        self._current_mode = ConnectionMode.VPN
        self._is_running = False
        self._connecting = False
        self._selected_profile: Optional[dict] = None

        # --- UI Components Placeholders ---
        self._heartbeat: Optional[ft.Container] = None
        self._server_list = None
        self._server_sheet: Optional[ft.BottomSheet] = None
        self._settings_drawer = None
        self._logs_drawer_component = None
        self._server_card = None
        self._connection_button = None
        self._status_display = None
        self._theme_icon = None
        self._header = None
        self._main_container = None
        self._splash = None

        # --- Initialization ---
        self._define_callbacks()
        self._setup_page()
        self._build_ui()
        self._setup_drawers()
        
        # Start background tasks
        self._page.run_task(self._start_ui_tasks)
        
        # Start Splash Sequence
        self._start_splash()

    # -----------------------------
    # Define callbacks
    # -----------------------------
    def _define_callbacks(self):
        self._on_connect_clicked = self._on_connect_clicked_impl
        self._open_server_drawer = self._open_server_drawer_impl
        self._open_logs_drawer = self._open_logs_drawer_impl
        self._open_settings_drawer = self._open_settings_drawer_impl

    # -----------------------------
    # Page setup
    # -----------------------------
    def _setup_page(self):
        self._page.title = "XenRay"
        self._page.window.width = 420
        self._page.window.height = 650
        self._page.window.resizable = False
        self._page.padding = 0
        self._page.theme_mode = ft.ThemeMode.DARK
        self._page.theme = ft.Theme(font_family="Roboto")
        self._page.fonts = {
            "Roboto": "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf",
            "RobotoBold": "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf",
        }

        icon_path = os.path.join(APPDIR, "assets", "icon.ico")
        if os.path.exists(icon_path):
            self._page.window_icon = icon_path

        saved_mode = self._config_manager.get_connection_mode()
        saved_theme = self._config_manager.get_theme_mode()
        
        self._current_mode = (
            ConnectionMode.VPN if saved_mode == "vpn" else ConnectionMode.PROXY
        )
        self._page.theme_mode = (
            ft.ThemeMode.DARK if saved_theme == "dark" else ft.ThemeMode.LIGHT
        )

    # -----------------------------
    # Helper: Thread-safe UI call
    # -----------------------------
    def _ui_call(self, fn: Callable, *args, **kwargs):
        """Wraps UI updates in an async task to be thread-safe."""
        async def _coro():
            try:
                fn(*args, **kwargs)
                try:
                    self._page.update()
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"UI call error: {e}")

        self._page.run_task(_coro)

    # -----------------------------
    # Build UI Structure
    # -----------------------------
    def _build_ui(self):
        # Header
        self._header = Header(
            self._page,
            self._toggle_theme,
            self._open_logs_drawer,
            self._open_settings_drawer
        )

        self._status_display = StatusDisplay()
        self._connection_button = ConnectionButton(on_click=self._on_connect_clicked)
        self._server_card = ServerCard(on_click=self._open_server_drawer)

        main_column = ft.Column(
            [
                self._header,
                ft.Container(height=50),
                ft.Container(expand=True),
                ft.Column(
                    [
                        self._connection_button,
                        ft.Container(height=20),
                        self._status_display,
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Container(expand=True),
                self._server_card,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._main_container = AppContainer(main_column)
        self._page.add(self._main_container)
        
        # Sync Initial Theme State
        is_dark = self._page.theme_mode == ft.ThemeMode.DARK
        self._main_container.update_theme(is_dark)
        self._connection_button.update_theme(is_dark) # Ensure button matches too
        self._server_card.update_theme(is_dark) # Ensure card matches too

    def _start_splash(self):
        """Initialize splash screen and show window."""
        def on_splash_finish(splash_instance):
             self._page.overlay.remove(splash_instance)
             self._page.update()

        self._splash = SplashOverlay(on_splash_finish)
        self._page.overlay.append(self._splash)
        self._page.update()
        
        # Center and Show Window
        self._page.window.width = 420
        self._page.window.height = 650
        self._page.window.center()
        self._page.window.visible = True
        self._page.update()

        # Start animation
        self._page.run_task(self._splash.fade_out)

    # -----------------------------
    # Setup Drawers & BottomSheet
    # -----------------------------
    def _setup_drawers(self):
        self._log_viewer = LogViewer("Connection Logs")
        self._log_viewer.set_page(self._page)

        # Local import to avoid circular dependency
        from src.ui.server_list import ServerList

        self._server_list = ServerList(self._config_manager, self._on_server_selected)
        self._server_list.set_page(self._page)

        self._heartbeat = ft.Container(
            width=8, height=8, bgcolor=ft.Colors.GREEN_400, border_radius=4, opacity=0
        )

        self._settings_drawer = SettingsDrawer(
            self._config_manager,
            self._run_specific_installer,
            self._on_mode_changed,
            lambda: self._current_mode,
        )

        self._logs_drawer_component = LogsDrawer(self._log_viewer, self._heartbeat)

        # Initialize BottomSheet
        self._server_sheet = ft.BottomSheet(
            ft.Container(content=self._server_list, padding=20, expand=True),
            open=False
        )
        
        # NOTE: Removed self._page.bottom_sheet assignment to use page.open() method

        # Load last used profile
        last_profile_id = self._config_manager.get_last_selected_profile_id()
        if last_profile_id:
            profiles = self._config_manager.load_profiles()
            for profile in profiles:
                if profile.get("id") == last_profile_id:
                    self._selected_profile = profile
                    self._server_card.update_server(profile)
                    break

    # -----------------------------
    # Logic: Button Clicks & Drawer Opens
    # -----------------------------
    def _on_connect_clicked_impl(self, e=None):
        if not self._selected_profile:
            self._show_snackbar("Please select a server first")
            return
        if self._connecting:
            self._show_snackbar("Connection in progress...")
            return
        
        if not self._is_running:
            self._connection_button.set_connecting()
            self._status_display.set_connecting()
            self._ui_call(lambda: None)
            self._connect_async()
        else:
            self._disconnect()

    def _open_server_drawer_impl(self, e=None):
        """Opens the server list using the modern page.open() method."""
        if self._server_sheet:
            self._page.open(self._server_sheet)
            self._safe_update_server_list()

    def _open_logs_drawer_impl(self, e=None):
        self._page.end_drawer = self._logs_drawer_component
        self._logs_drawer_component.open = True
        self._ui_call(lambda: None)

    def _open_settings_drawer_impl(self, e=None):
        self._page.end_drawer = self._settings_drawer
        self._settings_drawer.open = True
        self._ui_call(lambda: None)

    # -----------------------------
    # Logic: Server Selection
    # -----------------------------
    def _on_server_selected(self, profile: dict):
        def _apply():
            self._selected_profile = profile
            self._server_card.update_server(profile)
            self._server_sheet.open = False
            self._page.update() # Update page to close sheet

        self._ui_call(_apply)
        
        try:
            self._config_manager.set_last_selected_profile_id(profile.get("id"))
        except Exception:
            pass
            
        if self._is_running:
            self._disconnect()
            self._connect_async()

    def _safe_update_server_list(self):
        """Waits for the sheet to be mounted before updating list."""
        async def _wait_and_update():
            # Wait until the server list control is mounted to the page
            while self._server_list.page is None:
                await asyncio.sleep(0.05)
            
            try:
                self._server_list._load_profiles(update_ui=True)
            except Exception as ex:
                logger.debug(f"Error loading profiles: {ex}")

        self._page.run_task(_wait_and_update)

    # -----------------------------
    # Logic: Connection Management
    # -----------------------------
    def _connect_async(self):
        if self._connecting:
            return
        self._connecting = True
        
        profile_config = (
            self._selected_profile.get("config") if self._selected_profile else {}
        )
        mode_str = "vpn" if self._current_mode == ConnectionMode.VPN else "proxy"

        def connect_task():
            try:
                os.makedirs(TMPDIR, exist_ok=True)
                temp_config_path = os.path.join(TMPDIR, "current_config.json")
                with open(temp_config_path, "w", encoding="utf-8") as f:
                    json.dump(profile_config, f)

                def on_step(step_msg: str):
                    self._ui_call(self._status_display.set_step, step_msg)

                success = self._connection_manager.connect(
                    temp_config_path, mode_str, step_callback=on_step
                )
                
                if not success:
                    self._connecting = False
                    self._ui_call(self._reset_ui_disconnected)
                    self._show_snackbar("Connection Failed")
                    return

                self._is_running = True
                self._connecting = False
                
                self._ui_call(self._status_display.set_connected, True)
                self._ui_call(self._connection_button.set_connected)

                if self._current_mode == ConnectionMode.VPN:
                    self._log_viewer.start_tailing(XRAY_LOG_FILE, TUN_LOG_FILE)
                else:
                    self._log_viewer.start_tailing(XRAY_LOG_FILE)
            
            except Exception as e:
                logger.error(f"Error in connect_task: {e}")
                self._connecting = False
                self._ui_call(self._reset_ui_disconnected)

        threading.Thread(target=connect_task, daemon=True).start()

    def _disconnect(self):
        if not self._is_running:
            return
        self._is_running = False
        
        try:
            self._connection_manager.disconnect()
        except Exception:
            pass
            
        try:
            self._log_viewer.stop_tailing()
        except Exception:
            pass
            
        self._reset_ui_disconnected()
        self._show_snackbar("Disconnected")

    def _reset_ui_disconnected(self):
        self._is_running = False
        self._connecting = False
        try:
            self._connection_button.set_disconnected()
            self._status_display.set_disconnected(self._current_mode)
        except Exception:
            pass
        self._ui_call(lambda: None)

    # -----------------------------
    # Logic: Utilities
    # -----------------------------
    def _toggle_theme(self, e=None):
        is_dark = self._page.theme_mode == ft.ThemeMode.DARK
        self._page.theme_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        # Icon update handled by Header component now
        
        # Save preference
        self._config_manager.set_theme_mode("light" if is_dark else "dark")
        
        self._connection_button.update_theme(not is_dark)
        self._server_card.update_theme(not is_dark)
        self._main_container.update_theme(not is_dark)
        self._header.update_theme(not is_dark)
        self._ui_call(lambda: None)

    def _show_snackbar(self, message: str):
        def _set():
            self._page.open(ft.SnackBar(ft.Text(message)))
        self._ui_call(_set)

    def _run_specific_installer(self, component: str):
        progress = ft.ProgressRing()
        status = ft.Text(f"Updating {component}...")
        
        # Create a modal dialog instead of using overlay
        dialog = ft.AlertDialog(
            content=ft.Column(
                [progress, status], 
                alignment=ft.MainAxisAlignment.CENTER,
                height=100,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            modal=True,
        )
        
        self._page.open(dialog)

        def update_status(msg: str):
            status.value = msg
            status.update()

        def install_task():
            try:
                if component == "xray":
                    from src.services.xray_installer import XrayInstallerService
                    XrayInstallerService.install(
                        progress_callback=update_status,
                        stop_service_callback=self._connection_manager.disconnect,
                    )
                elif component == "geo":
                    from src.services.geo_installer import GeoInstallerService
                    GeoInstallerService.install(progress_callback=update_status)

                self._show_snackbar(f"{component} Update Complete!")
            except Exception as e:
                self._show_snackbar(f"Error: {e}")
            finally:
                self._ui_call(lambda: self._page.close(dialog))

        threading.Thread(target=install_task, daemon=True).start()

    def _on_mode_changed(self, mode: ConnectionMode):
        from src.utils.process_utils import ProcessUtils

        if mode == ConnectionMode.VPN and not ProcessUtils.is_admin():
            self._show_snackbar("Admin rights required for VPN mode")
            return
        
        self._current_mode = mode
        self._config_manager.set_connection_mode(
            "vpn" if mode == ConnectionMode.VPN else "proxy"
        )
        self._status_display.set_status(f"{mode.name} Mode Selected")
        self._ui_call(lambda: None)

    # -----------------------------
    # Background Tasks
    # -----------------------------
    async def _start_ui_tasks(self):
        """Manages background UI updates like heartbeat animation."""
        async def heartbeat_loop():
            while True:
                # Optimized heartbeat logic using Flet animation
                if self._is_running:
                     try:
                        if self._heartbeat.page:
                             # Toggle opacity
                             self._heartbeat.opacity = 0.2 if self._heartbeat.opacity == 1.0 else 1.0
                             self._heartbeat.update()
                     except:
                        pass
                else:
                    # Reset when not running
                     try:
                        if self._heartbeat.opacity != 0:
                            self._heartbeat.opacity = 0
                            self._heartbeat.update()
                     except:
                        pass
                
                await asyncio.sleep(1.0) # Matches animation duration approx

        self._page.run_task(heartbeat_loop)

    # -----------------------------
    # Cleanup
    # -----------------------------
    def cleanup(self):
        try:
            self._disconnect()
        except Exception:
            pass