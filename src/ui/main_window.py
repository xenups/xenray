from __future__ import annotations

import asyncio
import os
import threading
from typing import Callable, Optional

import flet as ft

# Local modules
from src.core.config_manager import ConfigManager
from src.core.connection_manager import ConnectionManager
from src.core.constants import (
    APPDIR,
    FONT_URLS,
)
from src.core.logger import logger
from src.core.types import ConnectionMode
from src.services.network_stats import NetworkStatsService
from src.utils.process_utils import ProcessUtils
from src.services.connection_tester import ConnectionTester
from src.ui.handlers.network_stats_handler import NetworkStatsHandler
from src.ui.handlers.connection_handler import ConnectionHandler
from src.ui.managers.drawer_manager import DrawerManager
from src.ui.builders.ui_builder import UIBuilder
from src.ui.helpers.glow_helper import GlowHelper


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

        # --- Services ---
        self._network_stats = NetworkStatsService()
        
        # --- Handlers ---
        self._network_stats_handler = NetworkStatsHandler(self)
        self._connection_handler = ConnectionHandler(self)
        self._drawer_manager = DrawerManager(self)
        self._ui_builder = UIBuilder(self)
        self._glow_helper = GlowHelper(self)

        # --- Initialization ---
        self._define_callbacks()
        self._setup_page()
        self._ui_builder.build_ui()  # Delegate to builder
        self._drawer_manager.setup_drawers()  # Delegate to manager

        # Start background tasks
        self._page.run_task(self._start_ui_tasks)

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
        # Window size/center already set in main() - just handle theme/styling here
        self._page.padding = 0
        self._page.theme_mode = ft.ThemeMode.DARK
        self._page.theme = ft.Theme(font_family="Roboto")
        self._page.fonts = FONT_URLS

        icon_path = os.path.join(APPDIR, "assets", "icon.ico")
        if os.path.exists(icon_path):
            self._page.window.icon = icon_path

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
    def _ui_call(self, fn: Callable, *args, update_page: bool = False, **kwargs):
        """Wraps UI updates in an async task to be thread-safe."""

        async def _coro():
            try:
                fn(*args, **kwargs)
                if update_page:
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
    # -----------------------------
    # Navigation & UI Building
    # -----------------------------
    def navigate_to(self, control: ft.Control):
        """Navigate to a new view (replaces dashboard)."""
        self._view_switcher.content = control
        self._view_switcher.update()

    def navigate_back(self, e=None):
        """Return to dashboard view."""
        self._view_switcher.content = self._dashboard_view
        self._view_switcher.update()

    def _create_dashboard_view(self):
        return ft.Column(
            [
                self._header,
                ft.Container(expand=True),
                # Connection Button in center
                self._connection_button,
                # Status Display directly below button (no gap)
                self._status_display,
                ft.Container(expand=True),
                # Server Card at bottom
                self._server_card,
            ],

            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.START,
            expand=True,
        )

    def _build_ui(self):
        """Deprecated - now handled by UIBuilder."""
        pass  # Builder handles initialization

    # -----------------------------
    # Setup Drawers & BottomSheet
    # -----------------------------
    def _setup_drawers(self):
        """Deprecated - now handled by DrawerManager."""
        pass  # Manager handles initialization

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

        # Admin Check for VPN Mode
        if not self._is_running:
            if self._current_mode == ConnectionMode.VPN:


                if not ProcessUtils.is_admin():
                    # CALL THE NEW CLASS METHOD
                    self._show_admin_restart_dialog()
                    return  # Stop execution if admin restart is needed

            self._connection_button.set_connecting()
            self._status_display.set_connecting()
            self._ui_call(lambda: None)
            self._connect_async()
        else:
            self._disconnect()

    def _show_admin_restart_dialog(self):
        """Shows an AlertDialog asking the user to restart the app as Admin."""


        page = self._page

        def close_dlg(e):
            page.close(dlg)

        def confirm_restart(e):
            page.close(dlg)
            # Save "VPN" mode so the app starts in VPN mode after restart
            self._config_manager.set_connection_mode(ConnectionMode.VPN.value)
            ProcessUtils.restart_as_admin()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Admin Rights Required"),
            content=ft.Text(
                "VPN mode requires Administrator privileges.\n\nDo you want to restart the application as Admin?"
            ),
            actions=[
                ft.TextButton("Cancel", on_click=close_dlg),
                ft.TextButton("Restart", on_click=confirm_restart),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        if page:
            page.open(dlg)

    def _open_server_drawer_impl(self, e=None):
        """Delegate to drawer manager."""
        self._drawer_manager.open_server_drawer(e)

    def _open_logs_drawer_impl(self, e=None):
        """Delegate to drawer manager."""
        self._drawer_manager.open_logs_drawer(e)

    def _open_settings_drawer_impl(self, e=None):
        """Delegate to drawer manager."""
        self._drawer_manager.open_settings_drawer(e)

    # -----------------------------
    # Logic: Server Selection
    # -----------------------------
    def _update_selected_profile_ui(self, profile: dict):
        """Updates the UI with the selected profile."""
        self._selected_profile = profile
        self._server_card.update_server(profile)
        self._server_sheet.open = False
        # Immediately update status display with country info (persistent)
        self._status_display.update_country(profile)
        self._page.update()  # Update page to close sheet

    def _handle_pre_connection_test(self, success, result_str, country_data, profile):
        """Handles the result of the pre-connection latency/country test."""
        if not self._is_running and not self._connecting:
            self._ui_call(
                self._status_display.set_pre_connection_ping,
                result_str,
                success,
            )
            # Update country if found
            if country_data and profile:
                profile.update(country_data)
                self._config_manager.update_profile(
                    profile.get("id"), country_data
                )
                # Update display
                self._ui_call(
                    lambda: self._status_display.update_country(country_data)
                )
                self._ui_call(lambda: self._server_card.update_server(profile))

                if country_data.get("country_code"):
                    self._ui_call(
                        self._server_list.update_item_icon,
                        profile.get("id"),
                        country_data.get("country_code"),
                    )

    def _trigger_reconnect(self):
        """Handle transparent reconnection when server changes while running."""
        # Use fast reconnect to avoid Disconnected/Disconnecting flicker
        self._connection_handler.reconnect()

    def _on_server_selected(self, profile: dict):
        # 1. Update UI Selection
        self._ui_call(lambda: self._update_selected_profile_ui(profile))

        try:
            self._config_manager.set_last_selected_profile_id(profile.get("id"))
        except Exception:
            pass

        # 2. Trigger immediate latency check if not running
        if not self._is_running and not self._connecting:
            self._ui_call(self._status_display.set_pre_connection_ping, "...", False)
            
            fetch_flag = not profile.get("country_code")
            ConnectionTester.test_connection(
                profile.get("config", {}), 
                lambda s, r, d=None: self._handle_pre_connection_test(s, r, d, profile), 
                fetch_country=fetch_flag
            )

        # 3. Handle live switch if running
        if self._is_running:
            self._trigger_reconnect()

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
    # Logic: Horizon Glow
    # -----------------------------
    def _update_horizon_glow(self, state: str):
        """Delegate to glow helper."""
        self._glow_helper.update_horizon_glow(state)

    # -----------------------------
    # Logic: Connection Management
    # -----------------------------
    def _connect_async(self):
        """Delegate to connection handler."""
        self._connection_handler.connect_async()

    def _start_monitoring_loop(self):
        """Runs periodic checks every 60s."""

        def _loop():
            # Initial wait for connection stabilize
            import time

            time.sleep(5)

            while self._is_running:
                # 1. Check Latency & Fetch Country if missing
                profile = self._selected_profile
                if not profile:
                    break

                # Fetch if city/country missing
                need_fetch = not profile.get("city") or not profile.get("country_code")

                # We use the ConnectionTester to do a ping + optionally fetch geoip
                from src.services.connection_tester import ConnectionTester

                success, result, country_data = ConnectionTester.test_connection_sync(
                    profile.get("config", {}), fetch_country=need_fetch
                )

                if success:
                    # FORCE UPDATE UI
                    logger.debug(f"Monitoring loop success. Country: {country_data}")
                    if country_data:
                        profile.update(country_data)
                        self._config_manager.update_profile(
                            profile.get("id"), country_data
                        )

                    # Visual Updates (Pass current profile state)
                    # We use lambda to capture specific values or allow delayed execution,
                    # but here we want to ensure self._selected_profile is read at call time.
                    self._ui_call(lambda: self._status_display.update_country(profile))
                    self._ui_call(lambda: self._server_card.update_server(profile))

                    if country_data and country_data.get("country_code"):
                        self._ui_call(
                            self._server_list.update_item_icon,
                            profile.get("id"),
                            country_data.get("country_code"),
                        )

                # Wait 60s
                for _ in range(60):
                    if not self._is_running:
                        return
                    time.sleep(1)

        threading.Thread(target=_loop, daemon=True).start()

    def _disconnect(self):
        """Delegate to connection handler."""
        self._connection_handler.disconnect()

    def _reset_ui_disconnected(self):
        """Delegate to connection handler."""
        self._connection_handler.reset_ui_disconnected()

    async def _ui_loop_network_stats(self):
        """
        Dedicated UI loop for network stats.
        Polls shared state from service and updates UI.
        Runs on main UI thread (Async), does NOT block.
        """
        while self._is_running:
            try:
                # 1. Timing Control (Frequency Rule: >= 1s, prefer 1.5s)
                await asyncio.sleep(1.5)
                
                if not self._is_running:
                    # Reset heartbeat if needed (idempotent check)
                    if self._heartbeat and self._heartbeat.opacity != 0:
                        self._heartbeat.opacity = 0
                        self._heartbeat.update()
                    
                    if not self._network_stats:
                        break
                    continue

                # 2. Lifecycle Check (Prevent Race Condition)
                # Ensure StatusDisplay is fully mounted and ready
                if not self._status_display or not self._status_display.page:
                    continue

                # 3. Read Shared State (Thread-Safe)
                stats = self._network_stats.get_stats()
                
                # 4. Update UI (Main Thread)
                # Stats come pre-formatted as strings (e.g., "1.5 MB/s")
                # Only total_bps is a raw float
                down_str = stats.get("download_speed", "0 B/s")
                up_str = stats.get("upload_speed", "0 B/s")
                
                try:
                    total_bps = float(stats.get("total_bps", 0))
                except (ValueError, TypeError):
                    total_bps = 0.0
                
                # Update Connection Button Glow based on network activity
                if self._connection_button and self._connection_button.page:
                    # Always update button glow - it will handle the intensity internally
                    self._connection_button.update_network_activity(total_bps)
                
                # Update LogsDrawer stats if open AND mounted
                if (self._logs_drawer_component 
                    and self._logs_drawer_component.open 
                    and self._logs_drawer_component.page):
                    # Speeds are already formatted strings, use them directly
                    self._logs_drawer_component.update_network_stats(
                        down_str, 
                        up_str
                    )

                # Earth Glow Animation (Sun Rays) - replaces button glow
                if self._earth_glow and self._earth_glow.page:
                    total_mbps = stats["total_bps"] / (1024 * 1024)
                    
                    # Calculate intensity (0.0 to 1.0)
                    intensity = min(1.0, total_mbps / 5.0) # Max glow at 5 MB/s
                    
                    # Base glow (Idle)
                    base_opacity = 0.3
                    base_scale = 1.0
                    
                    # Target glow (Active)
                    target_opacity = base_opacity + (0.5 * intensity)
                    target_scale = base_scale + (0.2 * intensity)
                    
                    self._earth_glow.opacity = target_opacity
                    self._earth_glow.scale = target_scale
                    self._earth_glow.update()

                # Button Glow - Disabled in Earth Theme
                # if self._connection_button and self._connection_button.page:
                #     self._connection_button.update_network_activity(stats["total_bps"])
                
                # 5. Heartbeat logic for LogsDrawer only - fade in/out only
                if self._logs_heartbeat and self._logs_heartbeat.page:
                    # Fade in/out animation without scale
                    is_bright = self._logs_heartbeat.opacity > 0.5
                    if is_bright:
                        self._logs_heartbeat.opacity = 0.3
                    else:
                        self._logs_heartbeat.opacity = 1.0
                    self._logs_heartbeat.update()

            except Exception as e:
                logger.error(f"Error in stats UI loop: {e}")
                await asyncio.sleep(1.5)

    # -----------------------------
    # Logic: Utilities
    # -----------------------------
    def _toggle_theme(self, e=None):
        is_dark = self._page.theme_mode == ft.ThemeMode.DARK
        self._page.theme_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        # Icon update handled by Header component now

        # Save preference in background to avoid blocking UI
        threading.Thread(
            target=self._config_manager.set_theme_mode,
            args=("light" if is_dark else "dark",),
            daemon=True,
        ).start()

        self._connection_button.update_theme(not is_dark)
        self._server_card.update_theme(not is_dark)
        # self._main_container.update_theme(not is_dark) # Removed in Earth theme
        self._header.update_theme(not is_dark)
        # Force a page update to ensure theme mode change applies globally
        self._page.update()

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
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
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

                self._show_snackbar(f"{component} Update Complete!")
            except Exception as e:
                self._show_snackbar(f"Error: {e}")
            finally:
                self._ui_call(lambda: self._page.close(dialog))

        threading.Thread(target=install_task, daemon=True).start()

    def _on_profile_updated(self, updated_profile: dict):
        """Called when ServerList updates a profile (e.g. latency test results)."""
        if not self._selected_profile:
            return

        # If the updated profile is the currently selected one, refresh the UI
        if updated_profile.get("id") == self._selected_profile.get("id"):
            # Update local reference
            self._selected_profile.update(updated_profile)
            # Update Status Display
            self._ui_call(lambda: self._status_display.update_country(updated_profile))
            # Update Server Card
            self._ui_call(
                lambda: self._server_card.update_server(self._selected_profile)
            )

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

        if self._is_running:
            # If already connected, use fast reconnect
            self._connection_handler.reconnect()

    # -----------------------------
    # Background Tasks
    # -----------------------------
    async def _start_ui_tasks(self):
        """Manages background UI updates like heartbeat animation."""
        
        # Start network stats loop
        self._page.run_task(self._network_stats_handler.run_stats_loop)

        async def monitor_latency_loop():
            """Continuously tests connectivity for selected profile when disconnected."""
            while True:
                if (
                    not self._is_running
                    and not self._connecting
                    and self._selected_profile
                ):
                    config = self._selected_profile.get("config", {})

                    def on_result(success, result_str, country_data=None):
                        if not self._is_running and not self._connecting:
                            self._ui_call(
                                self._status_display.set_pre_connection_ping,
                                result_str,
                                success,
                            )
                            # Update country if found
                            if country_data and self._selected_profile:
                                self._selected_profile.update(country_data)
                                self._config_manager.update_profile(
                                    self._selected_profile.get("id"), country_data
                                )
                                self._ui_call(
                                    self._status_display.update_country, country_data
                                )

                    from src.services.connection_tester import ConnectionTester

                    fetch_flag = not self._selected_profile.get("country_code")
                    ConnectionTester.test_connection(
                        config, on_result, fetch_country=fetch_flag
                    )

                # Check every 60s
                # We check every 1s to be responsive to state changes, but execute test every 60s
                for _ in range(60):
                    await asyncio.sleep(1)

        # self._page.run_task(monitor_latency_loop)

    # -----------------------------
    # Cleanup
    # -----------------------------
    def cleanup(self):
        try:
            self._disconnect()
        except Exception:
            pass
