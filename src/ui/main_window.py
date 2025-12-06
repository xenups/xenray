"""Flet-based main window - Modern UI Redesign."""

import os
import shutil
import threading
from typing import Optional

import flet as ft

from src.core.config_manager import ConfigManager
from src.core.connection_manager import ConnectionManager
from src.core.constants import TMPDIR, TUN_LOG_FILE, XRAY_LOG_FILE
from src.core.types import ConnectionMode
from src.ui.components.connection_button import ConnectionButton
from src.ui.components.logs_drawer import LogsDrawer
from src.ui.components.server_card import ServerCard
from src.ui.components.settings_drawer import SettingsDrawer
from src.ui.components.status_display import StatusDisplay
from src.ui.log_viewer import LogViewer
from src.core.logger import logger


class MainWindow:
    """Main Flet window - Modern UI."""

    def __init__(
        self,
        page: ft.Page,
        config_manager: ConfigManager,
        connection_manager: ConnectionManager,
    ):
        self._page = page
        self._config_manager = config_manager
        self._connection_manager = connection_manager

        # State
        self._current_mode = ConnectionMode.VPN
        self._is_running = False
        self._selected_file_path: Optional[str] = None
        self._connecting = False  # Lock to prevent concurrent connections
        self._selected_profile = None  # Selected server profile

        # Configure Page
        self._page.title = "XenRay"
        self._page.window_width = 420  # Slightly wider for better spacing
        self._page.window_height = 650  # Taller
        self._page.window_resizable = False
        self._page.padding = 0

        # Theme & Fonts
        self._page.theme_mode = ft.ThemeMode.DARK
        self._page.theme = ft.Theme(font_family="Roboto")  # Modern Font
        self._page.fonts = {
            "Roboto": "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf",
            "RobotoBold": "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf",
        }

        # Colors (Dynamic based on theme, but setting defaults for Dark)
        self._bg_color = ft.colors.BACKGROUND
        self._surface_color = ft.colors.SURFACE_VARIANT
        self._primary_color = ft.colors.PRIMARY

        # Load saved mode
        saved_mode = self._config_manager.get_connection_mode()
        self._current_mode = (
            ConnectionMode.VPN if saved_mode == "vpn" else ConnectionMode.PROXY
        )

        self._build_ui()

        # Check installations (Disabled auto-check)
        # self._check_installations()

    def _build_ui(self):
        """Build the modern user interface."""

        # --- Header ---
        # --- Header ---
        self._theme_icon = ft.IconButton(
            icon=(
                ft.icons.WB_SUNNY_OUTLINED
                if self._page.theme_mode == ft.ThemeMode.DARK
                else ft.icons.NIGHTLIGHT_ROUND
            ),
            icon_color=ft.colors.ON_SURFACE,
            tooltip="Toggle Theme",
            on_click=self._toggle_theme,
        )

        self._header = ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Icon(
                                ft.icons.SHIELD_MOON, color=ft.colors.PRIMARY, size=28
                            ),
                            ft.Text(
                                "XenRay",
                                size=24,
                                weight=ft.FontWeight.BOLD,
                                color=ft.colors.ON_SURFACE,
                            ),
                        ]
                    ),
                    ft.Row(
                        [
                            self._theme_icon,
                            ft.IconButton(
                                icon=ft.icons.ARTICLE_OUTLINED,
                                icon_color=ft.colors.ON_SURFACE,
                                tooltip="Logs",
                                on_click=self._open_logs_drawer,
                            ),
                            ft.IconButton(
                                icon=ft.icons.SETTINGS_OUTLINED,
                                icon_color=ft.colors.ON_SURFACE,
                                tooltip="Settings",
                                on_click=self._open_settings_drawer,
                            ),
                        ]
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.padding.symmetric(horizontal=20, vertical=20),
            bgcolor=ft.colors.SURFACE,  # Header background
            border=ft.border.only(
                bottom=ft.border.BorderSide(1, ft.colors.OUTLINE_VARIANT)
            ),
        )

        # --- Components ---
        self._status_display = StatusDisplay()
        self._connection_button = ConnectionButton(on_click=self._on_connect_clicked)
        self._server_card = ServerCard(on_click=self._open_server_drawer)

        # --- Main Layout ---
        self._main_container = ft.Container(
            expand=True,
            content=ft.Column(
                [   
                    self._header,
                    ft.Container(height=50),
                    ft.Container(expand=True),  # Pushes down
                    # ---- Center Area ----
                    ft.Column(
                        [
                            self._connection_button,
                            ft.Container(height=20),
                            self._status_display,
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Container(expand=True),  # Pushes up
                    self._server_card,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        self._page.add(self._main_container)

        # --- Drawers ---
        self._setup_drawers()

    def _setup_drawers(self):
        """Setup side drawers."""
        # Log Viewer
        self._log_viewer = LogViewer("Connection Logs")
        self._log_viewer.set_page(self._page)

        # Server List
        from src.ui.server_list import ServerList

        self._server_list = ServerList(self._config_manager, self._on_server_selected)

        # Heartbeat
        self._heartbeat = ft.Container(
            width=8,
            height=8,
            bgcolor=ft.colors.GREEN_400,
            border_radius=4,
            opacity=0,  # Start hidden
            animate_opacity=ft.animation.Animation(500, ft.AnimationCurve.EASE_IN_OUT),
        )
        # Start heartbeat thread
        threading.Thread(target=self._animate_heartbeat, daemon=True).start()

        # Settings Drawer
        self._settings_drawer = SettingsDrawer(
            self._config_manager,
            self._run_specific_installer,
            self._on_mode_changed,
            lambda: self._current_mode,
        )
        self._end_drawer = self._settings_drawer.build()

        # Logs Drawer
        self._logs_drawer_component = LogsDrawer(self._log_viewer, self._heartbeat)
        self._logs_drawer = self._logs_drawer_component.build()

        # Bottom Sheet (Server List)
        self._server_sheet = ft.BottomSheet(
            ft.Container(
                self._server_list,
                padding=20,
                height=400,
            ),
            open=False,
        )
        self._page.bottom_sheet = self._server_sheet

        # Auto-select last selected profile
        last_profile_id = self._config_manager.get_last_selected_profile_id()
        if last_profile_id:
            profiles = self._config_manager.load_profiles()
            for profile in profiles:
                if profile["id"] == last_profile_id:
                    self._selected_profile = profile
                    self._server_card.update_server(profile)
                    break

    def _open_settings_drawer(self, e):
        self._page.end_drawer = self._end_drawer
        self._page.show_end_drawer(self._end_drawer)

    def _open_logs_drawer(self, e):
        self._page.end_drawer = self._logs_drawer
        self._page.show_end_drawer(self._logs_drawer)

    def _open_server_drawer(self, e):
        self._server_sheet.open = True
        self._server_list._load_profiles(update_ui=False)
        self._page.update()

    def _on_server_selected(self, profile):
        # Update UI first
        self._selected_profile = profile
        self._server_card.update_server(profile)
        self._server_sheet.open = False
        self._page.update()

        # Save last selected profile
        self._config_manager.set_last_selected_profile_id(profile["id"])

        # Seamless Switching
        if self._is_running:
            logger.debug("Switching server while connected...")
            # 1. Disconnect current (synchronous/fast)
            self._disconnect()

            # 2. Connect to new (async)
            # We need to wait a tiny bit for disconnect to fully clear?
            # _disconnect is synchronous now, so it should be fine.
            self._connect_async()

    def _on_mode_changed(self, mode: ConnectionMode):
        from src.utils.process_utils import ProcessUtils

        if mode == ConnectionMode.VPN:
            # Check for admin privileges for VPN mode
            if not ProcessUtils.is_admin():
                self._show_admin_dialog()
                return

            self._current_mode = ConnectionMode.VPN
            self._status_display.set_status("VPN Mode Selected")
            self._config_manager.set_connection_mode("vpn")
        else:
            self._current_mode = ConnectionMode.PROXY
            self._status_display.set_status("Proxy Mode Selected")
            self._config_manager.set_connection_mode("proxy")
        self._page.update()

    def _show_admin_dialog(self):
        """Show dialog requesting admin privileges."""

        def restart_admin(e):
            self._admin_dialog.open = False
            self._page.update()
            self._restart_as_admin()

        self._admin_dialog = ft.AlertDialog(
            title=ft.Text("Administrator Privileges Required"),
            content=ft.Text(
                "VPN mode requires Administrator privileges to modify system routing.\n\nWould you like to restart the application as Administrator?"
            ),
            actions=[
                ft.TextButton("Restart as Admin", on_click=restart_admin),
                ft.TextButton("Cancel", on_click=lambda e: self._close_admin_dialog()),
            ],
        )
        self._page.dialog = self._admin_dialog
        self._admin_dialog.open = True
        self._page.update()

    def _close_admin_dialog(self):
        self._admin_dialog.open = False
        self._page.update()

    def _restart_as_admin(self):
        """Restart the application with admin privileges."""
        import ctypes
        import sys

        if os.name == "nt":
            # Re-run the current script with admin rights
            # We need to use the python executable and the script path
            params = " ".join([f'"{arg}"' for arg in sys.argv])
            try:
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, params, None, 1
                )
                # Exit current instance
                self.cleanup()
                self._page.window.destroy()
                os._exit(0)
            except Exception as e:
                logger.error(f"Failed to restart as admin: {e}")
                self._show_snackbar("Failed to restart as admin")

    # --- Connection Logic ---

    def _on_connect_clicked(self, e):
        if not self._selected_profile:
            self._show_snackbar("Please select a server first")
            return

        if self._connecting:
            self._show_snackbar("Connection in progress...")
            return

        if not self._is_running:
            # Connect Animation
            self._connection_button.set_connecting()
            self._status_display.set_connecting()
            self._page.update()

            # Run asynchronously to prevent UI freeze
            self._connect_async()
        else:
            # Disconnect
            self._disconnect()

    def _connect_async(self):
        """Connect asynchronously with safe UI updates."""
        logger.debug("_connect_async started")
        if self._connecting:
            logger.debug("Already connecting, returning")
            return

        self._connecting = True
        logger.debug(f"Set _connecting=True, _is_running={self._is_running}")
        mode_str = "vpn" if self._current_mode == ConnectionMode.VPN else "proxy"

        # Capture necessary data for the thread
        profile_config = self._selected_profile["config"]

        def connect_task():
            # Write temporary config file from profile
            import json

            temp_config_path = os.path.join(TMPDIR, "current_config.json")
            os.makedirs(TMPDIR, exist_ok=True)
            with open(temp_config_path, "w") as f:
                json.dump(profile_config, f)
            logger.debug(f"Config written to {temp_config_path}")

            # Step callback to update status display text
            def on_step(step_msg):
                try:
                    self._status_display.set_step(step_msg)
                except:
                    pass  # Ignore UI errors in callback

            # Perform connection (blocking I/O)
            success = self._connection_manager.connect(temp_config_path, mode_str, step_callback=on_step)
            logger.debug(f"Connection result: {success}")

            # Schedule UI update on main thread
            async def update_ui():
                if not success:
                    self._connecting = False
                    logger.debug("Connection failed, resetting UI")
                    self._reset_ui_disconnected()
                    self._show_snackbar("Connection Failed")
                    return

                # Success UI Update
                logger.debug("Connection successful, updating UI")
                self._is_running = True
                self._connecting = False

                # Start combined logs
                if self._current_mode == ConnectionMode.VPN:
                    self._log_viewer.start_tailing(XRAY_LOG_FILE, TUN_LOG_FILE)
                else:
                    self._log_viewer.start_tailing(XRAY_LOG_FILE)

                # Animate Button to Connected State
                logger.debug("Updating button UI")
                self._connection_button.set_connected()
                self._status_display.set_connected(self._current_mode)
                logger.debug("Calling page.update()")
                self._page.update()
                logger.debug("page.update() completed")

            # Run UI update safely
            self._page.run_task(update_ui)

        # Start background thread
        threading.Thread(target=connect_task, daemon=True).start()

    def _disconnect(self):
        """Disconnect synchronously (optimized to be fast)."""
        logger.debug(f"_disconnect called, _is_running={self._is_running}")

        if not self._is_running:
            logger.debug("Not running, returning")
            return

        self._is_running = False
        logger.debug("Calling connection_manager.disconnect()")
        self._connection_manager.disconnect()
        logger.debug("Stopping log tailing")
        self._log_viewer.stop_tailing()
        logger.debug("Resetting UI")
        self._reset_ui_disconnected()
        logger.debug("Showing snackbar")
        self._show_snackbar("Disconnected")
        logger.debug("_disconnect completed")

    def _reset_ui_disconnected(self):
        self._is_running = False
        self._connection_button.set_disconnected()
        self._status_display.set_disconnected(self._current_mode)
        self._page.update()

    def _show_snackbar(self, message: str):
        self._page.snack_bar = ft.SnackBar(ft.Text(message))
        self._page.snack_bar.open = True
        self._page.update()

    def cleanup(self):
        """Cleanup on app close - just disconnect, logs cleared on next startup."""
        self._disconnect()

    # --- Installation Logic ---
    def _check_installations(self):
        from src.services.dependency_manager import DependencyManager

        missing = DependencyManager.check_installed()
        if missing:
            self._show_install_dialog(missing_items=missing)

    def _show_install_dialog(self, force: bool = False, missing_items: list = None):
        items_str = ", ".join(missing_items) if missing_items else "Core Components"
        title = "Reinstall Components" if force else "Missing Components"
        content = (
            f"Reinstalling {items_str}..."
            if force
            else f"Required components ({items_str}) are missing. Install now?"
        )

        def start_install(e):
            self._install_dialog.open = False
            self._page.update()
            self._run_installer(force)

        self._install_dialog = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(content),
            actions=[
                ft.TextButton("Install", on_click=start_install),
                ft.TextButton("Cancel", on_click=lambda e: self._close_dialog()),
            ],
        )
        self._page.dialog = self._install_dialog
        self._install_dialog.open = True
        self._page.update()

    def _close_dialog(self):
        self._install_dialog.open = False
        self._page.update()

    def _run_installer(self, force: bool):
        # Overlay UI
        progress = ft.ProgressRing()
        status = ft.Text("Initializing...")
        overlay = ft.Container(
            content=ft.Column(
                [progress, status],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=ft.colors.BLACK87,
            alignment=ft.alignment.center,
        )
        self._page.overlay.append(overlay)
        self._page.update()

        def update_status(msg):
            status.value = msg
            self._page.update()

        def install_task():
            from src.services.dependency_manager import DependencyManager

            try:
                # Hack: Delete files if force
                if force:
                    from src.core.constants import XRAY_EXECUTABLE

                    if os.path.exists(XRAY_EXECUTABLE):
                        try:
                            os.remove(XRAY_EXECUTABLE)
                        except:
                            pass

                DependencyManager.install_all(progress_callback=update_status)

                self._show_snackbar("Installation Complete!")
            except Exception as e:
                self._show_snackbar(f"Error: {e}")
            finally:
                self._page.overlay.remove(overlay)
                self._page.update()

        threading.Thread(target=install_task, daemon=True).start()

    def _toggle_theme(self, e):
        """Toggle between Light and Dark mode."""
        if self._page.theme_mode == ft.ThemeMode.DARK:
            self._page.theme_mode = ft.ThemeMode.LIGHT
            self._page.bgcolor = ft.colors.BACKGROUND  # Light background
            self._theme_icon.icon = ft.icons.NIGHTLIGHT_ROUND
            self._connection_button.update_theme(False)
            self._server_card.update_theme(False)
        else:
            self._page.theme_mode = ft.ThemeMode.DARK
            self._page.bgcolor = ft.colors.BACKGROUND  # Dark background
            self._theme_icon.icon = ft.icons.WB_SUNNY_OUTLINED
            self._connection_button.update_theme(True)
            self._server_card.update_theme(True)
        self._page.update()

    def _animate_heartbeat(self):
        """Animate the heartbeat circle."""
        import time

        while True:
            # Wait until attached to page
            if not self._heartbeat.page:
                time.sleep(1)
                continue

            # Only animate if running
            if not self._is_running:
                if self._heartbeat.opacity != 0:
                    self._heartbeat.opacity = 0
                    self._heartbeat.update()
                time.sleep(1)
                continue

            try:
                # Pulse Fade
                self._heartbeat.opacity = 1.0
                self._heartbeat.update()
                time.sleep(0.8)
                self._heartbeat.opacity = 0.2
                self._heartbeat.update()
                time.sleep(0.8)
            except Exception:
                # Handle cases where update fails (e.g. page closed)
                break

    def _on_port_changed(self, e):
        try:
            port = int(self._port_field.value)
            if 1024 <= port <= 65535:
                self._config_manager.set_proxy_port(port)
            else:
                # Invalid port range, maybe show error or ignore
                pass
        except ValueError:
            pass

    def _run_specific_installer(self, component: str):
        # Overlay UI
        progress = ft.ProgressRing()
        status = ft.Text(f"Updating {component}...")
        overlay = ft.Container(
            content=ft.Column(
                [progress, status],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=ft.colors.BLACK87,
            alignment=ft.alignment.center,
        )
        self._page.overlay.append(overlay)
        self._page.update()

        def update_status(msg):
            status.value = msg
            self._page.update()

        def install_task():
            from src.services.xray_installer import XrayInstallerService
            from src.services.geo_installer import GeoInstallerService

            try:
                if component == "xray":
                    # Pass callback to stop xray service after download, before extraction
                    XrayInstallerService.install(
                        progress_callback=update_status,
                        stop_service_callback=self._connection_manager.disconnect
                    )
                elif component == "geo":
                    GeoInstallerService.install(progress_callback=update_status)

                self._show_snackbar(f"{component} Update Complete!")
            except Exception as e:
                self._show_snackbar(f"Error: {e}")
            finally:
                self._page.overlay.remove(overlay)
                self._page.update()

        threading.Thread(target=install_task, daemon=True).start()
