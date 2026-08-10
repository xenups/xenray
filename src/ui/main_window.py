from __future__ import annotations

import asyncio
import os
from typing import Optional

import flet as ft

# Local modules
from src.core.app_context import AppContext
from src.core.connection_manager import ConnectionManager
from src.core.constants import FONT_URLS, WINDOW_HEIGHT, WINDOW_WIDTH
from src.core.i18n import t
from src.core.logger import logger
from src.core.types import ConnectionMode
from src.services.network_stats import NetworkStatsService
from src.ui.builders.ui_builder import UIBuilder
from src.ui.components.add_server_dialog import AddServerDialog
from src.ui.components.admin_restart_dialog import AdminRestartDialog
from src.ui.components.close_dialog import CloseDialog
from src.ui.components.lan_sharing_card import LanSharingCard
from src.ui.components.settings_sections import (
    AutoReconnectToggleRow,
    CountryDropdownRow,
    LanguageDropdownRow,
    ModeSwitchRow,
    PortInputRow,
    StartupToggleRow,
)
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
from src.ui.helpers.profile_presenter import ProfilePresenter
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
        self._active_tab = "dashboard"
        self._nav_locked = False

        # --- UI Components Placeholders ---
        self._heartbeat: Optional[ft.Container] = None
        self._server_list = None
        self._server_sheet: Optional[ft.BottomSheet] = None
        self._settings_drawer = None
        self._logs_drawer_component = None
        self._server_card = None
        self._connection_button = None
        self._status_display = None
        self._lan_sharing_card = None
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

        self._ui_builder.build_core_components()  # Step 1: legacy components
        self._drawer_manager.setup_drawers()  # Delegate to manager
        self._ui_builder.build_stitch_views()  # Step 2: Stitch views + layout (after drawers)

        # Forward last selected profile to new Stitch views (loaded by setup_drawers)
        if self._selected_profile:
            self._update_selected_profile_ui(self._selected_profile)

        # Sync initial connection state to all new views
        self._sync_dashboard_connection_state()

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

        # Wire LAN sharing card visibility into the connection lifecycle.
        self._connection_handler._lan_card_callback = lambda show: (
            self._lan_sharing_card.set_visible(show) if self._lan_sharing_card else None
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
            active_tab_getter=lambda: self._active_tab,
        )

        # Wrap status_display to forward step messages to the new dashboard view
        self._wrap_status_display()

        self._background_task_handler.setup(page=self._page)
        self._systray.setup(self)

        # Start background tasks
        self._background_task_handler.start()

        # Initialize UI with selected profile if exists
        if self._selected_profile:
            self._update_selected_profile_ui(self._selected_profile)

        # Start forwarding tasks for new Stitch views
        self._page.run_task(self._forward_network_stats)
        self._page.run_task(self._forward_system_stats)

    async def _forward_network_stats(self):
        """Periodically forward network stats to new views."""
        import asyncio

        # Session accumulators (bytes)
        _session_dl_bytes: float = 0.0
        _session_ul_bytes: float = 0.0
        _was_running: bool = False
        _interval: float = 3.0

        while True:
            try:
                await asyncio.sleep(_interval)
                is_running = self._is_running

                # Reset session totals when a new connection starts
                if is_running and not _was_running:
                    _session_dl_bytes = 0.0
                    _session_ul_bytes = 0.0
                _was_running = is_running

                if not is_running or self._nav_locked:
                    continue

                stats = self._network_stats.get_stats()
                down_str = stats.get("download_speed", "0 B/s")
                up_str = stats.get("upload_speed", "0 B/s")
                total_bps = float(stats.get("total_bps", 0))

                # Real dl/ul bps from stats (use 60/40 split as estimate)
                dl_bps = total_bps * 0.6
                ul_bps = total_bps * 0.4

                # Accumulate session totals
                _session_dl_bytes += dl_bps * _interval
                _session_ul_bytes += ul_bps * _interval

                def _fmt_bytes(b: float) -> str:
                    if b < 1024:
                        return f"{b:.0f} B"
                    if b < 1024 * 1024:
                        return f"{b / 1024:.1f} KB"
                    if b < 1024 * 1024 * 1024:
                        return f"{b / (1024 * 1024):.1f} MB"
                    return f"{b / (1024 * 1024 * 1024):.2f} GB"

                dl_total_str = _fmt_bytes(_session_dl_bytes)
                ul_total_str = _fmt_bytes(_session_ul_bytes)

                kwargs = dict(
                    rate_str=down_str,
                    upload_str=ul_total_str,
                    download_str=dl_total_str,
                    download_bps=dl_bps,
                    upload_bps=ul_bps,
                    total_bps=total_bps,
                    download_total=dl_total_str,
                    upload_total=ul_total_str,
                )

                # Only update the view that is currently visible
                if (
                    self._active_tab == "dashboard"
                    and hasattr(self, "_stitch_dashboard_view")
                    and self._stitch_dashboard_view
                ):
                    self._stitch_dashboard_view.update_network_stats(**kwargs)
                elif (
                    self._active_tab == "statistics"
                    and hasattr(self, "_stitch_statistics_view")
                    and self._stitch_statistics_view
                ):
                    self._stitch_statistics_view.update_network_stats(**kwargs)
            except Exception:
                pass

    async def _forward_system_stats(self):
        """Periodically forward system stats (memory, threads, health) to LogsView."""
        import asyncio
        import os
        import threading

        import psutil

        while True:
            try:
                await asyncio.sleep(3.0)
                if self._nav_locked:
                    continue
                # Only gather and push system stats when logs tab is visible
                if self._active_tab != "logs":
                    continue
                process = psutil.Process()
                mem_info = process.memory_info()
                used_mb = mem_info.rss / (1024 * 1024)
                total_mb = psutil.virtual_memory().total / (1024 * 1024)
                thread_count = threading.active_count()
                health_issues = 0

                if hasattr(self, "_stitch_logs_view") and self._stitch_logs_view:
                    self._stitch_logs_view.update_memory(used_mb, total_mb)
                    self._stitch_logs_view.update_threads(thread_count)
                    self._stitch_logs_view.update_health(health_issues)
            except Exception:
                pass

    def _wrap_status_display(self):
        """Wrap status_display methods to forward step messages to dashboard view."""
        if not self._status_display:
            return
        sd = self._status_display

        # Forward set_step to dashboard
        orig_set_step = sd.set_step

        def wrapped_set_step(msg):
            orig_set_step(msg)
            try:
                if (
                    hasattr(self, "_stitch_dashboard_view")
                    and self._stitch_dashboard_view
                ):
                    self._stitch_dashboard_view.set_step(msg)
            except Exception:
                pass

        sd.set_step = wrapped_set_step

        # Forward set_connecting
        orig_set_connecting = sd.set_connecting

        def wrapped_set_connecting():
            orig_set_connecting()
            try:
                if (
                    hasattr(self, "_stitch_dashboard_view")
                    and self._stitch_dashboard_view
                ):
                    self._stitch_dashboard_view.set_connection_state(
                        is_connected=False, is_connecting=True
                    )
            except Exception:
                pass

        sd.set_connecting = wrapped_set_connecting

        # Forward set_connected
        orig_set_connected = sd.set_connected

        def wrapped_set_connected(country_data=None):
            orig_set_connected(country_data)
            try:
                if (
                    hasattr(self, "_stitch_dashboard_view")
                    and self._stitch_dashboard_view
                ):
                    self._stitch_dashboard_view.set_connection_state(is_connected=True)
            except Exception:
                pass

        sd.set_connected = wrapped_set_connected

        # Forward set_disconnected
        orig_set_disconnected = sd.set_disconnected

        def wrapped_set_disconnected():
            orig_set_disconnected()
            try:
                if (
                    hasattr(self, "_stitch_dashboard_view")
                    and self._stitch_dashboard_view
                ):
                    self._stitch_dashboard_view.set_connection_state(is_connected=False)
            except Exception:
                pass

        sd.set_disconnected = wrapped_set_disconnected

        # Forward set_disconnecting
        orig_set_disconnecting = sd.set_disconnecting

        def wrapped_set_disconnecting():
            orig_set_disconnecting()
            try:
                if (
                    hasattr(self, "_stitch_dashboard_view")
                    and self._stitch_dashboard_view
                ):
                    self._stitch_dashboard_view.set_connection_state(
                        is_connected=False, is_disconnecting=True
                    )
            except Exception:
                pass

        sd.set_disconnecting = wrapped_set_disconnecting

    # --- State Helpers (for handlers) ---
    def _set_is_running(self, val: bool):
        self._is_running = val
        self._sync_dashboard_connection_state()

    def _set_connecting(self, val: bool):
        self._connecting = val
        self._sync_dashboard_connection_state()

    def _set_profile_manager_running(self, val: bool):
        self._profile_manager.is_running = val

    def _sync_dashboard_connection_state(self):
        """Sync the dashboard view's connection state with current state."""
        try:
            if hasattr(self, "_stitch_dashboard_view") and self._stitch_dashboard_view:
                self._stitch_dashboard_view.set_connection_state(
                    is_connected=self._is_running,
                    is_connecting=self._connecting,
                )
            if (
                hasattr(self, "_stitch_statistics_view")
                and self._stitch_statistics_view
            ):
                self._stitch_statistics_view.set_connection_state(
                    is_connected=self._is_running,
                    is_connecting=self._connecting,
                )
            if hasattr(self, "_nav_sidebar") and self._nav_sidebar:
                server_name = (
                    self._selected_profile.get("name", "")
                    if self._selected_profile
                    else ""
                )
                self._nav_sidebar.update_connect_button_text(
                    text="Disconnect" if self._is_running else "Connect",
                    is_running=self._is_running,
                    server_name=server_name,
                )
        except Exception:
            pass

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

        from src.main import get_absolute_icon_path

        icon_path = get_absolute_icon_path()
        if os.path.exists(icon_path):
            self._page.window.icon = icon_path

        saved_mode = self._app_context.settings.get_connection_mode()
        saved_theme = self._app_context.settings.get_theme_mode()

        self._current_mode = (
            ConnectionMode.VPN if saved_mode == "vpn" else ConnectionMode.PROXY
        )
        self._page.theme_mode = (
            ft.ThemeMode.DARK if saved_theme == "dark" else ft.ThemeMode.LIGHT
        )

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
        """Navigate to a new view — suppress background updates during swap."""
        self._nav_locked = True
        self._view_switcher.content = control
        self._view_switcher.update()
        self._nav_locked = False

    def _on_server_search(self, query: str):
        """Handle server search in ServersView."""
        if self._profile_manager:
            self._server_list._load_profiles(search_query=query, update_ui=True)

    def _open_add_server_dialog(self, e=None):
        """Open the add server dialog."""
        self._show_add_server_dialog()

    def navigate_back(self, e=None):
        """Return to settings view or active tab from subpages."""
        target_tab = (
            self._active_tab
            if self._active_tab in ("settings", "statistics", "servers", "logs")
            else "settings"
        )
        self._on_nav_tab_changed(target_tab)

    def _on_nav_tab_changed(self, tab_id: str):
        """Switch the main content view based on the selected nav tab.

        Uses targeted ``control.update()`` on just the view-switcher and
        sidebar buttons instead of ``page.update()`` to avoid serializing
        the entire page control tree.
        """
        if self._active_tab == tab_id:
            return
        self._active_tab = tab_id
        view_map = {
            "dashboard": self._stitch_dashboard_view,
            "statistics": self._stitch_statistics_view,
            "servers": self._stitch_servers_view,
            "logs": self._stitch_logs_view,
            "settings": self._stitch_settings_view,
        }
        target = view_map.get(tab_id, self._dashboard_view)

        # Mutate both controls before flushing to the client
        self._view_switcher.content = target
        if hasattr(self, "_nav_sidebar") and self._nav_sidebar:
            self._nav_sidebar._active_tab = tab_id
            self._nav_sidebar._apply_active_styles()

        # Targeted updates — only send the changed subtrees, not the entire page
        self._view_switcher.update()
        if hasattr(self, "_nav_sidebar") and self._nav_sidebar:
            self._nav_sidebar._buttons_container.update()

        # Update log viewer visibility (only live-stream logs when viewing logs tab or drawer)
        if hasattr(self, "_log_viewer") and self._log_viewer:
            drawer_open = (
                getattr(self._logs_drawer_component, "open", False)
                if hasattr(self, "_logs_drawer_component")
                and self._logs_drawer_component
                else False
            )
            self._log_viewer.set_visible(tab_id == "logs" or drawer_open)

    def _create_dashboard_view(self):
        if not self._lan_sharing_card:
            self._lan_sharing_card = LanSharingCard(self._app_context)

        # Central block containing Power Button & Status Display with top margin offset
        center_block = ft.Container(
            content=ft.Column(
                [
                    self._connection_button,
                    self._status_display,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=0,
            ),
            margin=ft.Margin.only(top=20),
        )

        return ft.Column(
            [
                self._header,
                ft.Container(expand=True),
                center_block,
                ft.Container(expand=True),
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
            self._sync_dashboard_connection_state()
            self._ui_helper.call(lambda: None)
            self._connect_async()
        else:
            # Show disconnecting state in dashboard
            try:
                if (
                    hasattr(self, "_stitch_dashboard_view")
                    and self._stitch_dashboard_view
                ):
                    self._stitch_dashboard_view.set_connection_state(
                        is_connected=False, is_disconnecting=True
                    )
            except Exception:
                pass
            self._disconnect()

    def _show_admin_restart_dialog(self):
        """Shows an AlertDialog asking the user to restart the app as Admin."""
        dialog = AdminRestartDialog(on_restart=self._on_admin_restart_confirmed)
        self._page.show_dialog(dialog)

    def _on_admin_restart_confirmed(self):
        """Callback from AdminRestartDialog."""
        # Save "VPN" mode so the app starts in VPN mode after restart
        self._app_context.settings.set_connection_mode(ConnectionMode.VPN.value)
        ProcessUtils.restart_as_admin()

    def _open_server_drawer_impl(self, e=None):
        """Delegate to drawer manager."""
        self._drawer_manager.open_server_drawer(e)

    async def _open_logs_drawer_impl(self, e=None):
        """Delegate to drawer manager."""
        await self._drawer_manager.open_logs_drawer(e)

    async def _open_settings_drawer_impl(self, e=None):
        """Delegate to drawer manager."""
        await self._drawer_manager.open_settings_drawer(e)

    # -----------------------------
    # Logic: Server Selection
    # -----------------------------
    def _update_selected_profile_ui(self, profile: dict):
        """Updates the UI with the selected profile."""
        self._selected_profile = profile
        self._server_card.update_server(profile)

        try:
            info = ProfilePresenter.extract_profile_info(profile)
            name = profile.get("name", "") or profile.get("remark", "")
            latency = info.get("latency", "--")
            country_code = info.get("country_code", "")
            country_name = info.get("country_name", "")
            protocol = info.get("protocol", "")
            encryption = info.get("encryption", "")
            server_ip = info.get("server_ip", "")

            # Update dashboard view
            if hasattr(self, "_stitch_dashboard_view") and self._stitch_dashboard_view:
                self._stitch_dashboard_view.update_server_info(
                    name=name,
                    latency=latency,
                    protocol=protocol,
                    encryption=encryption,
                    server_ip=server_ip,
                    country_code=country_code,
                    country_name=country_name,
                )

            # Update servers view hero node
            if hasattr(self, "_stitch_servers_view") and self._stitch_servers_view:
                self._stitch_servers_view.update_hero_node(
                    name=name,
                    latency=latency,
                    protocol=protocol,
                    country_code=country_code,
                )

            # Update statistics view
            if (
                hasattr(self, "_stitch_statistics_view")
                and self._stitch_statistics_view
            ):
                self._stitch_statistics_view.update_server_info(
                    name=name,
                    country_code=country_code,
                    server_ip=server_ip,
                )
        except Exception:
            pass

        if self._server_sheet:
            try:
                if self._server_sheet.open:
                    self._server_sheet.open = False
                    self._server_sheet.update()
            except Exception:
                pass
        # Targeted update — server_card was mutated above but not flushed
        try:
            if self._server_card and self._server_card.page:
                self._server_card.update()
        except Exception:
            pass

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
            self._ui_helper.call(
                self._status_display.set_pre_connection_ping, "...", False
            )
            self._latency_monitor_handler.trigger_single_check()

        # 3. Handle live switch if running
        if self._is_running:
            self._trigger_reconnect()

        # 4. Navigate back to dashboard automatically
        self._on_nav_tab_changed("dashboard")

    def _safe_update_server_list(self):
        """Waits for the sheet to be mounted before updating list."""

        async def _wait_and_update():
            while True:
                try:
                    if self._server_list.page is not None:
                        break
                except RuntimeError:
                    pass
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
    def _show_add_server_dialog(self):
        """Show the add server/subscription dialog."""
        dialog = AddServerDialog(
            on_server_added=lambda name, config: self._add_server_profile(name, config),
            on_subscription_added=lambda name, url: self._add_subscription(name, url),
            on_close=lambda: self._page.pop_dialog(),
            on_create_chain=None,
        )
        self._page.show_dialog(dialog)

    def _add_server_profile(self, name: str, config: dict):
        """Save a newly added server profile and refresh the server list."""
        self._app_context.profiles.save(name, config)
        if self._server_list:
            self._server_list._load_profiles(update_ui=True)

    def _add_subscription(self, name: str, url: str):
        """Save a newly added subscription and refresh the server list."""
        self._app_context.subscriptions.save(name, url)
        if self._server_list:
            self._server_list._load_profiles(update_ui=True)

    def _copy_logs(self):
        """Copy logs to clipboard."""
        if self._log_viewer:
            self._log_viewer.copy_to_clipboard()
            self._show_toast("Logs copied to clipboard", "success")

    def _download_logs(self):
        """Download logs to file."""
        if self._log_viewer:
            self._log_viewer.export_logs()
            self._show_toast("Logs exported", "success")

    def _clear_logs(self):
        """Clear log viewer."""
        if self._log_viewer:
            self._log_viewer.clear_logs()

    def _open_routing_page(self):
        """Navigate to routing page."""
        from src.ui.pages.routing_page import RoutingPage

        page = RoutingPage(
            app_context=self._app_context,
            on_back=self.navigate_back,
        )
        self.navigate_to(page)

    def _open_dns_page(self):
        """Navigate to DNS management page."""
        from src.ui.pages.dns_page import DNSPage

        page = DNSPage(
            app_context=self._app_context,
            on_back=self.navigate_back,
        )
        self.navigate_to(page)

    # --- Settings Row Builders ---
    def _build_mode_switch_row(self) -> ModeSwitchRow:
        is_proxy = self._current_mode == ConnectionMode.PROXY
        row = ModeSwitchRow(
            is_proxy=is_proxy,
            on_change=lambda e: self._on_mode_changed(
                ConnectionMode.PROXY if e.control.value else ConnectionMode.VPN
            ),
        )
        return row

    def _build_port_row(self) -> PortInputRow:
        return PortInputRow(
            initial_value=self._app_context.settings.get_proxy_port(),
            on_save=lambda val: self._save_port(val),
        )

    def _build_country_row(self) -> CountryDropdownRow:
        return CountryDropdownRow(
            current_value=self._app_context.settings.get_routing_country() or "",
            on_change=lambda code: self._app_context.settings.set_routing_country(code),
        )

    def _build_language_row(self) -> LanguageDropdownRow:
        return LanguageDropdownRow(
            current_value=self._app_context.settings.get_language() or "en",
            on_change=lambda code: self._change_language(code),
        )

    def _build_reconnect_row(self) -> AutoReconnectToggleRow:
        return AutoReconnectToggleRow(
            app_context=self._app_context,
            toast_callback=lambda msg, typ: self._show_toast(msg, typ),
        )

    def _build_startup_row(self) -> StartupToggleRow:
        from src.services.task_scheduler import (
            is_task_registered,
            is_supported,
            register_task,
            unregister_task,
        )

        return StartupToggleRow(
            app_context=self._app_context,
            is_registered=is_task_registered(),
            is_supported=is_supported(),
            on_register=register_task,
            on_unregister=unregister_task,
            toast_callback=self._show_toast,
        )

        return StartupToggleRow(
            app_context=self._app_context,
            is_registered=is_registered(),
            is_supported=is_supported(),
            on_register=lambda: register_startup(),
            on_unregister=lambda: unregister_startup(),
            toast_callback=lambda msg, typ: self._show_toast(msg, typ),
        )

    def _save_port(self, val):
        """Save proxy port setting."""
        try:
            port = int(val) if hasattr(val, "control") else int(val)
            self._app_context.settings.set_proxy_port(port)
            self._show_toast(f"SOCKS Port saved: {port}", "success")
        except (ValueError, TypeError):
            self._show_toast("Invalid port", "error")

    @staticmethod
    def _change_language(code: str):
        """Change application language."""
        from src.core.i18n import set_language

        set_language(code)

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
            self._ui_helper.call(
                lambda: self._server_card.update_server(self._selected_profile)
            )

    def _on_mode_changed(self, mode: ConnectionMode):
        from src.utils.process_utils import ProcessUtils

        if mode == ConnectionMode.VPN and not ProcessUtils.is_admin():
            self._show_toast(t("status.admin_required"), "warning")
            return

        self._current_mode = mode
        self._app_context.settings.set_connection_mode(
            "vpn" if mode == ConnectionMode.VPN else "proxy"
        )
        self._status_display.set_status(
            t("status.mode_selected", mode=mode.name.title())
        )
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
        """Show the close confirmation dialog."""
        logger.debug("[DEBUG] MainWindow.show_close_dialog() called")

        dialog = CloseDialog(
            on_exit=self._on_close_dialog_exit,
            on_minimize=self._minimize_to_tray,
            app_context=self._app_context,
        )
        self._page.show_dialog(dialog)

    def _on_close_dialog_exit(self):
        """Exit handler — triggers clean shutdown."""
        self.cleanup()
        from src.main import signal_exit

        signal_exit()
        from src.utils.process_utils import ProcessUtils

        ProcessUtils.kill_process_tree()
        os._exit(0)

    def _minimize_to_tray(self):
        """Hide window to tray (visible=False is safe with prevent_close=True)."""
        self._page.window.visible = False
        self._page.update()

    def _restore_from_tray(self):
        """Restore window from tray — re-locks dimensions, then reveals."""

        async def _show():
            try:
                self._page.window.width = WINDOW_WIDTH
                self._page.window.height = WINDOW_HEIGHT
                self._page.window.min_width = 620
                self._page.window.min_height = 480
                self._page.window.max_width = 620
                self._page.window.max_height = 480
                self._page.window.resizable = False
                self._page.window.maximizable = False
                self._page.window.visible = True
                self._page.window.minimized = False
                self._page.update()
                await self._page.window.to_front()
            except Exception:
                pass

        self._page.run_task(_show)

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
            self._connection_manager.cleanup()
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
        try:
            from src.utils.firewall_manager import FirewallManager

            FirewallManager.remove_lan_firewall_rule()
        except Exception:
            pass
