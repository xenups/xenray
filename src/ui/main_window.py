from __future__ import annotations

import asyncio
import os
from typing import Optional

import flet as ft

# Local modules
from src.core.app_context import AppContext
from src.core.connection_manager import ConnectionManager
from src.core.constants import APPDIR, FONT_URLS
from src.core.i18n import t
from src.core.logger import logger
from src.core.types import ConnectionMode
from src.services.network_stats import NetworkStatsService
from src.ui.builders.ui_builder import UIBuilder
from src.ui.components.admin_restart_dialog import AdminRestartDialog
from src.ui.components.close_dialog import CloseDialog
from src.ui.components.toast import ToastManager
from src.ui.handlers.background_task_handler import BackgroundTaskHandler
from src.ui.handlers.connection_handler import ConnectionHandler
from src.ui.handlers.installer_handler import InstallerHandler
from src.ui.handlers.latency_monitor_handler import LatencyMonitorHandler
from src.ui.handlers.network_stats_handler import NetworkStatsHandler
from src.ui.handlers.reconnect_event_handler import ReconnectEventHandler
from src.ui.handlers.systray_handler import SystrayHandler
from src.ui.handlers.theme_handler import ThemeHandler
from src.ui.helpers.glow_helper import GlowHelper
from src.ui.helpers.ui_thread_helper import UIThreadHelper
from src.ui.managers.drawer_manager import DrawerManager
from src.ui.managers.monitoring_service import MonitoringService
from src.ui.managers.profile_manager import ProfileManager
from src.utils.process_utils import ProcessUtils


class MainWindow:
    """Main Flet window for XenRay application."""

    def __init__(
        self,
        page: ft.Page,
        app_context: AppContext,
        connection_manager: ConnectionManager,
        network_stats: NetworkStatsService,
        network_stats_handler: NetworkStatsHandler,
        latency_monitor_handler: LatencyMonitorHandler,
        connection_handler: ConnectionHandler,
        reconnect_event_handler: ReconnectEventHandler,
        theme_handler: ThemeHandler,
        installer_handler: InstallerHandler,
        background_task_handler: BackgroundTaskHandler,
        systray_handler: SystrayHandler,
        profile_manager: ProfileManager,
        monitoring_service: MonitoringService,
    ):
        self._page = page

        # Injected Dependencies
        self._app_context = app_context
        self._connection_manager = connection_manager
        self._network_stats = network_stats

        # Injected Handlers
        self._network_stats_handler = network_stats_handler
        self._latency_monitor_handler = latency_monitor_handler
        self._connection_handler = connection_handler
        self._theme_handler = theme_handler
        self._installer_handler = installer_handler
        self._background_task_handler = background_task_handler
        self._systray = systray_handler
        self._reconnect_event_handler = reconnect_event_handler

        # Initialize UI thread helper
        self._ui_helper = UIThreadHelper(page)

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
        self._log_viewer = None  # Will be initialized by DrawerManager
        self._earth_glow = None
        self._logs_heartbeat = None

        # --- Management components ---
        self._drawer_manager = DrawerManager(self)
        self._ui_builder = UIBuilder(self)
        self._glow_helper = GlowHelper(self)

        # --- Toast Manager ---
        self._toast = None  # Will be initialized after page setup

        # --- Initialization ---
        self._define_callbacks()
        self._setup_page()

        # Initialize toast manager after page setup
        self._toast = ToastManager(self._page)
        # Store in page for components to access
        self._page._toast_manager = self._toast

        self._profile_manager = profile_manager
        self._profile_manager.setup(ui_updater=self._ui_helper.call)
        self._profile_manager.set_ui_update_callback(self._update_selected_profile_ui)

        self._monitoring_service = monitoring_service
        self._monitoring_service.setup(
            ui_updater=self._ui_helper.call,
            toast_manager=self._toast,
        )

        self._ui_builder.build_ui()  # Delegate to builder
        self._drawer_manager.setup_drawers()  # Delegate to manager

        # --- Bind Handlers (Post-UI Build) ---
        self._connection_handler.setup(
            ui_helper=self._ui_helper,
            connection_button=self._connection_button,
            status_display=self._status_display,
            log_viewer=self._log_viewer,
            toast=self._toast,
            systray=self._systray,
            logs_drawer_component=self._logs_drawer_component,
            latency_monitor_handler=self._latency_monitor_handler,
            is_running_getter=lambda: self._is_running,
            is_running_setter=self._set_is_running,
            connecting_getter=lambda: self._connecting,
            connecting_setter=self._set_connecting,
            selected_profile_getter=lambda: self._selected_profile,
            current_mode_getter=lambda: self._current_mode,
            update_horizon_glow_callback=self._update_horizon_glow,
            profile_manager_is_running_setter=self._set_profile_manager_running,
            monitoring_service_is_running_setter=self._set_monitoring_service_running,
        )

        # Setup reconnect event handler (for passive reconnect UI)
        self._reconnect_event_handler.setup(
            ui_helper=self._ui_helper,
            toast=self._toast,
            status_display=self._status_display,
            connection_button=self._connection_button,
            systray=self._systray,
            update_horizon_glow_callback=self._update_horizon_glow,
            is_running_setter=self._set_is_running,
            profile_manager_is_running_setter=self._set_profile_manager_running,
            monitoring_service_is_running_setter=self._set_monitoring_service_running,
            reset_ui_callback=self._reset_ui_disconnected,
        )

        self._theme_handler.setup(
            page=self._page,
            connection_button=self._connection_button,
            server_card=self._server_card,
            header=self._header,
        )

        self._installer_handler.setup(
            page=self._page,
            ui_helper=self._ui_helper,
            toast=self._toast,
        )

        self._latency_monitor_handler.setup(
            page=self._page,
            status_display=self._status_display,
            server_card=self._server_card,
            server_list=self._server_list,
            ui_helper=self._ui_helper,
            is_running_getter=lambda: self._is_running,
            connecting_getter=lambda: self._connecting,
            selected_profile_getter=lambda: self._selected_profile,
        )

        self._network_stats_handler.setup(
            page=self._page,
            status_display=self._status_display,
            connection_button=self._connection_button,
            logs_drawer_component=self._logs_drawer_component,
            earth_glow=self._earth_glow,
            logs_heartbeat=self._logs_heartbeat,
            heartbeat=self._heartbeat,
            is_running_getter=lambda: self._is_running,
        )

        self._background_task_handler.setup(page=self._page)
        self._systray.setup(self)

        # Start background tasks
        self._background_task_handler.start()

        # Initialize UI with selected profile if exists
        if self._selected_profile:
            self._update_selected_profile_ui(self._selected_profile)

    # --- State Helpers (for handlers) ---
    def _set_is_running(self, val: bool):
        self._is_running = val

    def _set_connecting(self, val: bool):
        self._connecting = val

    def _set_profile_manager_running(self, val: bool):
        self._profile_manager.is_running = val

    def _set_monitoring_service_running(self, val: bool):
        self._monitoring_service.is_running = val

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
        # Window icons already set in main() - just handle theme/styling here
        self._page.padding = 0
        self._page.theme_mode = ft.ThemeMode.DARK
        self._page.theme = ft.Theme(font_family="Roboto")
        self._page.fonts = FONT_URLS

        icon_path = os.path.join(APPDIR, "assets", "icon.ico")
        if os.path.exists(icon_path):
            self._page.window.icon = icon_path

        saved_mode = self._app_context.settings.get_connection_mode()
        saved_theme = self._app_context.settings.get_theme_mode()

        self._current_mode = ConnectionMode.VPN if saved_mode == "vpn" else ConnectionMode.PROXY
        self._page.theme_mode = ft.ThemeMode.DARK if saved_theme == "dark" else ft.ThemeMode.LIGHT

        # Load last selected profile (from local OR subscriptions)
        last_profile_id = self._app_context.settings.get_last_selected_profile_id()
        if last_profile_id:
            profile = self._app_context.get_profile_by_id(last_profile_id)
            if profile:
                self._selected_profile = profile
                # We can't update UI here as it's not built yet, but we set the state
                # The components (ServerCard, StatusDisplay) will need to be updated after build or in __init__

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

    # -----------------------------
    # Logic: Button Clicks & Drawer Opens
    # -----------------------------
    def _on_connect_clicked_impl(self, e=None):
        if not self._selected_profile:
            self._show_toast(t("status.select_server"), "warning")
            return
        if self._connecting:
            self._show_toast(t("status.connection_in_progress"))
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
            self._ui_helper.call(lambda: None)
            self._connect_async()
        else:
            self._disconnect()

    def _show_admin_restart_dialog(self):
        """Shows an AlertDialog asking the user to restart the app as Admin."""
        dialog = AdminRestartDialog(on_restart=self._on_admin_restart_confirmed)
        self._page.open(dialog)

    def _on_admin_restart_confirmed(self):
        """Callback from AdminRestartDialog."""
        # Save "VPN" mode so the app starts in VPN mode after restart
        self._app_context.settings.set_connection_mode(ConnectionMode.VPN.value)
        ProcessUtils.restart_as_admin()

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
        self._page.update()  # Update page to close sheet

    def _trigger_reconnect(self):
        """Handle transparent reconnection when server changes while running."""
        # Use fast reconnect to avoid Disconnected/Disconnecting flicker
        self._connection_handler.reconnect()

    def _on_server_selected(self, profile: dict):
        # 1. Update UI Selection
        self._ui_helper.call(lambda: self._update_selected_profile_ui(profile))

        try:
            self._app_context.settings.set_last_selected_profile_id(profile.get("id"))
        except Exception:
            pass

        # 2. Trigger immediate latency check via dedicated handler
        if not self._is_running and not self._connecting:
            self._ui_helper.call(self._status_display.set_pre_connection_ping, "...", False)
            self._latency_monitor_handler.trigger_single_check()

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

    def _disconnect(self):
        """Delegate to connection handler."""
        self._connection_handler.disconnect()

    def _reset_ui_disconnected(self):
        """Delegate to connection handler."""
        self._connection_handler.reset_ui_disconnected()

    # -----------------------------
    # Logic: Utilities
    # -----------------------------
    def _toggle_theme(self, e=None):
        """Delegate to theme handler."""
        self._theme_handler.toggle_theme(e)

    def _show_toast(self, message: str, message_type: str = "info"):
        """Show a toast notification."""
        if self._toast:
            self._toast.show(message, message_type)

    def _run_specific_installer(self, component: str):
        """Delegate to installer handler."""
        self._installer_handler.run_specific_installer(component)

    def _on_profile_updated(self, updated_profile: dict):
        """Called when ServerList updates a profile (e.g. latency test results)."""
        if not self._selected_profile:
            return

        # If the updated profile is the currently selected one, refresh the UI
        if updated_profile.get("id") == self._selected_profile.get("id"):
            # Update local reference
            self._selected_profile.update(updated_profile)
            # Update Server Card
            self._ui_helper.call(lambda: self._server_card.update_server(self._selected_profile))

    def _on_mode_changed(self, mode: ConnectionMode):
        from src.utils.process_utils import ProcessUtils

        if mode == ConnectionMode.VPN and not ProcessUtils.is_admin():
            self._show_toast(t("status.admin_required"), "warning")
            return

        self._current_mode = mode
        self._app_context.settings.set_connection_mode("vpn" if mode == ConnectionMode.VPN else "proxy")
        self._status_display.set_status(t("status.mode_selected", mode=mode.name.title()))
        self._ui_helper.call(lambda: None)

        if self._is_running:
            # If already connected, use fast reconnect
            self._connection_handler.reconnect()

    # -----------------------------
    # Background Tasks
    # -----------------------------

    # -----------------------------
    # Close Dialog
    # -----------------------------
    def show_close_dialog(self):
        """Public method to trigger the close confirmation dialog."""
        logger.debug("[DEBUG] MainWindow.show_close_dialog() called")

        # Check if user already chose to always minimize
        if self._app_context.settings.get_remember_close_choice():
            logger.debug("[DEBUG] Remembered choice found: Always minimize")
            self._handle_minimize_action()
            return

        dialog = CloseDialog(
            on_exit=self._on_close_dialog_exit,
            on_minimize=self._handle_minimize_action,
            app_context=self._app_context,
        )
        self._page.overlay.append(dialog)
        dialog.open = True
        self._page.update()
        logger.debug("[DEBUG] Redesigned close dialog opened")

    def _on_close_dialog_exit(self):
        """Unified exit handler for the app."""
        self.cleanup()
        from src.utils.process_utils import ProcessUtils

        ProcessUtils.kill_process_tree()
        os._exit(0)

    def _handle_minimize_action(self):
        """Helper to minimize window to tray."""
        self._page.window.visible = False
        self._page.window.skip_task_bar = True
        self._page.update()

    # -----------------------------
    # Cleanup
    # -----------------------------
    def cleanup(self):
        """Cleanup resources before exit."""
        logger.info("Cleaning up MainWindow resources...")
        try:
            self._network_stats.stop()
        except Exception:
            pass
        try:
            self._connection_manager.disconnect()
        except Exception:
            pass
        try:
            self._systray.stop()
        except Exception:
            pass
        try:
            self._reconnect_event_handler.cleanup()
        except Exception:
            pass
