"""Main Window Coordinator - layout assembly shell connecting views, navigation, lifecycle, and event bus."""

from __future__ import annotations

from typing import Optional

import flet as ft

from src.core.app_context import AppContext
from src.core.connection_manager import ConnectionManager
from src.core.constants import FONT_URLS
from src.core.i18n import t
from src.core.types import ConnectionMode
from src.services.network_stats import NetworkStatsService
from src.ui.builders.ui_builder import UIBuilder
from src.ui.components.common.admin_restart_dialog import AdminRestartDialog
from src.ui.components.common.toast import ToastManager
from src.ui.components.settings import (
    AutoReconnectToggleRow,
    CountryDropdownRow,
    LanguageDropdownRow,
    ModeSwitchRow,
    PortInputRow,
    StartupToggleRow,
)
from src.ui.handlers.background_task_handler import BackgroundTaskHandler
from src.ui.handlers.connection_handler import ConnectionHandler
from src.ui.handlers.installer_handler import InstallerHandler
from src.ui.handlers.latency_monitor_handler import LatencyMonitorHandler
from src.ui.handlers.network_stats_handler import NetworkStatsHandler
from src.ui.handlers.profile_selection_handler import ProfileSelectionHandler
from src.ui.handlers.reconnect_event_handler import ReconnectEventHandler
from src.ui.handlers.systray_handler import SystrayHandler
from src.ui.handlers.theme_handler import ThemeHandler
from src.ui.handlers.window_lifecycle_handler import WindowLifecycleHandler
from src.ui.helpers.glow_helper import GlowHelper
from src.ui.helpers.settings_form_helper import SettingsFormHelper
from src.ui.helpers.ui_thread_helper import UIThreadHelper
from src.ui.managers.drawer_manager import DrawerManager
from src.ui.managers.monitoring_service import MonitoringService
from src.ui.managers.profile_manager import ProfileManager
from src.ui.services.handler_binding_service import HandlerBindingService
from src.ui.services.navigation_service import NavigationService
from src.ui.services.stats_forwarding_service import StatsForwardingService
from src.utils.process_utils import ProcessUtils


class MainWindow:
    """Lightweight MainWindow coordinator delegating sub-responsibilities to specialized services and handlers."""

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
    ) -> None:
        self._page = page
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

        self._ui_helper = UIThreadHelper(page)

        # State Variables
        self._current_mode = ConnectionMode.VPN
        self._is_running = False
        self._connecting = False
        self._selected_profile: Optional[dict] = None
        self._active_tab = "dashboard"
        self._nav_locked = False

        # Placeholders
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
        self._log_viewer = None
        self._earth_glow = None
        self._logs_heartbeat = None

        # Managers & Sub-Services
        from src.core.startup_warmup_manager import StartupWarmupManager

        self._startup_warmup_manager = StartupWarmupManager(self)
        self._drawer_manager = DrawerManager(self)
        self._ui_builder = UIBuilder(self)
        self._glow_helper = GlowHelper(self)
        self._lifecycle_handler = WindowLifecycleHandler(self)
        self._navigation_service = NavigationService(self)
        self._stats_forwarding = StatsForwardingService(self)
        self._settings_helper = SettingsFormHelper(self)
        self._profile_selection_handler = ProfileSelectionHandler(self)
        self._handler_binding_service = HandlerBindingService(self)

        self._define_callbacks()
        self._setup_page()

        self._toast = ToastManager(self._page)
        self._page._toast_manager = self._toast

        self._profile_manager = profile_manager
        self._profile_manager.setup(ui_updater=self._ui_helper.call)
        self._profile_manager.set_ui_update_callback(self._update_selected_profile_ui)

        self._monitoring_service = monitoring_service
        self._monitoring_service.setup(ui_updater=self._ui_helper.call, toast_manager=self._toast)

        self._ui_builder.build_core_components()
        self._drawer_manager.setup_drawers()
        self._ui_builder.build_stitch_views()

        if self._selected_profile:
            self._update_selected_profile_ui(self._selected_profile)

        self._sync_dashboard_connection_state()
        self._handler_binding_service.bind_handlers()

        # NOTE: The startup active-server ping is now dispatched by the
        # StartupWarmupManager pipeline (PRIORITY_MANUAL, awaited during the
        # splash) — no redundant immediate trigger here.

    def start_warmup_pipeline(self) -> None:
        """Trigger background startup pre-warming and splash screen fade-out."""
        if hasattr(self, "_splash_screen") and self._splash_screen:
            self._splash_screen.trigger_entrance_animation()

            async def _run_warmup():
                # run_task requires a coroutine function — pass the bound async
                # method (with its kwarg), NOT a lambda wrapping it.
                warmup_task = self._page.run_task(
                    self._startup_warmup_manager.execute_startup_pipeline,
                    progress_callback=self._splash_screen.update_status if self._splash_screen else None,
                )
                await self._splash_screen.dismiss_when_ready(warmup_task)

            self._page.run_task(_run_warmup)
        else:
            self._page.run_task(self._startup_warmup_manager.execute_startup_pipeline)

    # --- Navigation & Subpage Forwarders ---
    def navigate_to(self, control: ft.Control) -> None:
        self._navigation_service.navigate_to(control)

    def navigate_back(self, e: Optional[ft.ControlEvent] = None) -> None:
        self._navigation_service.navigate_back(e)

    def _on_nav_tab_changed(self, tab_id: str, force: bool = False) -> None:
        self._navigation_service.on_nav_tab_changed(tab_id, force=force)

    def _open_routing_page(self) -> None:
        self._navigation_service.open_routing_page()

    def _open_dns_page(self) -> None:
        self._navigation_service.open_dns_page()

    def _open_lan_page(self) -> None:
        self._navigation_service.open_lan_page()

    def _on_server_search(self, query: str) -> None:
        self._navigation_service.on_server_search(query)

    def _open_add_server_dialog(self, e: Optional[ft.ControlEvent] = None) -> None:
        self._navigation_service.open_add_server_dialog(e)

    # --- Profile Selection Forwarders ---
    def _update_selected_profile_ui(self, profile: dict) -> None:
        self._profile_selection_handler.update_selected_profile_ui(profile)

    def _on_server_selected(self, profile: dict) -> None:
        self._profile_selection_handler.on_server_selected(profile)

    # --- Settings Form Forwarders ---
    def _on_mode_changed(self, mode: ConnectionMode) -> None:
        self._settings_helper.on_mode_changed(mode)

    def _build_mode_switch_row(self) -> ModeSwitchRow:
        return self._settings_helper.build_mode_switch_row()

    def _build_port_row(self) -> PortInputRow:
        return self._settings_helper.build_port_row()

    def _build_country_row(self) -> CountryDropdownRow:
        return self._settings_helper.build_country_row()

    def _build_language_row(self) -> LanguageDropdownRow:
        return self._settings_helper.build_language_row()

    def _build_reconnect_row(self) -> AutoReconnectToggleRow:
        return self._settings_helper.build_reconnect_row()

    def _build_startup_row(self) -> StartupToggleRow:
        return self._settings_helper.build_startup_row()

    # --- Lifecycle Forwarders ---
    def show_close_dialog(self) -> None:
        self._lifecycle_handler.show_close_dialog()

    def _minimize_to_tray(self) -> None:
        self._lifecycle_handler.minimize_to_tray()

    def _restore_from_tray(self) -> None:
        self._lifecycle_handler.restore_from_tray()

    def cleanup(self) -> None:
        self._lifecycle_handler.cleanup()

    # --- State & Callbacks ---
    def _set_is_running(self, val: bool) -> None:
        self._is_running = val
        self._sync_dashboard_connection_state()

    def _set_connecting(self, val: bool) -> None:
        self._connecting = val
        self._sync_dashboard_connection_state()

    def _set_profile_manager_running(self, val: bool) -> None:
        self._profile_manager.is_running = val

    def _set_monitoring_service_running(self, val: bool) -> None:
        self._monitoring_service.is_running = val

    def _sync_dashboard_connection_state(self) -> None:
        try:
            # FSM is the single source of truth for the connection lifecycle.
            # While it is STOPPING (process teardown in progress), the sync must
            # preserve the existing red disconnecting animation instead of forcing
            # the button straight back to DISCONNECTED (which would cut the pulse).
            from src.core.fsm.connection_fsm import ConnectionState, connection_fsm

            is_disconnecting = connection_fsm.state == ConnectionState.STOPPING

            if hasattr(self, "_stitch_dashboard_view") and self._stitch_dashboard_view:
                self._stitch_dashboard_view.set_connection_state(
                    is_connected=self._is_running,
                    is_connecting=self._connecting,
                    is_disconnecting=is_disconnecting,
                )
            if hasattr(self, "_stitch_statistics_view") and self._stitch_statistics_view:
                self._stitch_statistics_view.set_connection_state(
                    is_connected=self._is_running,
                    is_connecting=self._connecting,
                    is_disconnecting=is_disconnecting,
                )
            if hasattr(self, "_nav_sidebar") and self._nav_sidebar:
                server_name = self._selected_profile.get("name", "") if self._selected_profile else ""
                self._nav_sidebar.update_connect_button_text(
                    text="Disconnect" if self._is_running else "Connect",
                    is_running=self._is_running,
                    server_name=server_name,
                )
        except Exception:
            pass

    def _define_callbacks(self) -> None:
        self._on_connect_clicked = self._on_connect_clicked_impl
        self._open_server_drawer = self._drawer_manager.open_server_drawer
        self._open_logs_drawer = self._drawer_manager.open_logs_drawer
        self._open_settings_drawer = self._drawer_manager.open_settings_drawer

    def _setup_page(self) -> None:
        self._page.padding = 0
        self._page.theme_mode = ft.ThemeMode.DARK
        self._page.theme = ft.Theme(font_family="Roboto")
        self._page.fonts = FONT_URLS

        saved_mode = self._app_context.settings.get_connection_mode()
        saved_theme = self._app_context.settings.get_theme_mode()

        self._current_mode = ConnectionMode.VPN if saved_mode == "vpn" else ConnectionMode.PROXY
        self._page.theme_mode = ft.ThemeMode.DARK if saved_theme == "dark" else ft.ThemeMode.LIGHT

        last_profile_id = self._app_context.settings.get_last_selected_profile_id()
        if last_profile_id:
            profile = self._app_context.get_profile_by_id(last_profile_id)
            if profile:
                self._selected_profile = profile

    def _create_dashboard_view(self) -> ft.Column:
        return self._ui_builder.create_dashboard_view()

    def _on_connect_clicked_impl(self, e=None) -> None:
        from src.core.event_bus import EVENT_DISCONNECT_REQUESTED, event_bus
        from src.core.fsm.connection_fsm import ConnectionState, connection_fsm

        if not self._selected_profile:
            self._show_toast(t("status.select_server"), "warning")
            return

        current_state = connection_fsm.state
        if current_state == ConnectionState.PINGING:
            # User clicked Connect during the initial ping check: cancel the
            # background probe, stop the neon sweep instantly, and let the
            # engine startup take over (FSM PINGING -> STARTING is driven by
            # the engine's "connecting" event).
            self._cancel_active_ping()
            current_state = connection_fsm.state
        if (
            self._is_running
            or self._connecting
            or current_state
            in {
                ConnectionState.CONNECTED,
                ConnectionState.STARTING,
                ConnectionState.PREPARING,
            }
        ):
            event_bus.publish(EVENT_DISCONNECT_REQUESTED)
            self._disconnect()
            return

        if self._current_mode == ConnectionMode.VPN and not ProcessUtils.is_admin():
            self._show_admin_restart_dialog()
            return

        self._connect_async()

    def _cancel_active_ping(self) -> None:
        """Cancel the in-flight initial ping and stop its neon sweep (in-place).

        Used when the user clicks Connect while the FSM is in PINGING: the
        background probe is dropped (its result can never clobber the newer
        connect state) and the sweep disc is cleared instantly.
        """
        try:
            if self._latency_monitor_handler:
                key = self._latency_monitor_handler.cancel_active_ping()
                if key:
                    from src.services.ping_service import ping_manager

                    ping_manager.cancel(key)
        except Exception:
            pass
        try:
            if self._connection_button:
                self._connection_button.stop_ping_animation()
        except Exception:
            pass

    def _show_admin_restart_dialog(self) -> None:
        dialog = AdminRestartDialog(on_restart=self._on_admin_restart_confirmed)
        self._page.show_dialog(dialog)

    def _on_admin_restart_confirmed(self) -> None:
        self._app_context.settings.set_connection_mode(ConnectionMode.VPN.value)
        ProcessUtils.restart_as_admin()

    def _trigger_reconnect(self) -> None:
        self._connection_handler.reconnect()

    def _update_horizon_glow(self, state: str) -> None:
        self._glow_helper.update_horizon_glow(state)

    def _connect_async(self) -> None:
        self._connection_handler.connect_async()

    def _disconnect(self) -> None:
        self._connection_handler.disconnect()

    def _reset_ui_disconnected(self) -> None:
        self._connection_handler.reset_ui_disconnected()

    def _on_core_crashed(self, payload=None) -> None:
        """Reactive handler for EVENT_CORE_CRASHED.

        Drives the UI (button/status/glow/LAN card) back to a clean DISCONNECTED
        state and notifies the user, ensuring the app never stays stuck showing
        CONNECTED after a sing-box/Xray-core crash. Runs on the CoreHealthMonitor
        background thread, so all Flet mutations are marshaled to the event loop.
        """
        self._ui_helper.call(self._apply_core_crash_ui)

    def _apply_core_crash_ui(self) -> None:
        try:
            if self._connection_handler:
                self._connection_handler._stop_network_stats()
                self._connection_handler.reset_ui_disconnected()
            self._show_toast(t("connection.core_crashed"), "error")
            if self._systray:
                try:
                    self._systray.update_state()
                except Exception:
                    pass
        except Exception as e:
            from loguru import logger

            logger.warning(f"[MainWindow] Core crash UI reset error: {e}")

    def _copy_logs(self) -> None:
        if self._log_viewer:
            self._log_viewer.copy_to_clipboard()
            self._show_toast("Logs copied to clipboard", "success")

    def _download_logs(self) -> None:
        if self._log_viewer:
            self._log_viewer.export_logs()
            self._show_toast("Logs exported", "success")

    def _clear_logs(self) -> None:
        if self._log_viewer:
            self._log_viewer.clear_logs()

    def _toggle_theme(self, e=None) -> None:
        self._theme_handler.toggle_theme(e)

    def _show_toast(self, message: str, message_type: str = "info") -> None:
        if self._toast:
            self._toast.show(message, message_type)

    def _run_specific_installer(self, component: str) -> None:
        self._installer_handler.run_specific_installer(component)

    def _on_profile_updated(self, updated_profile: dict) -> None:
        if not self._selected_profile:
            return
        if updated_profile.get("id") == self._selected_profile.get("id"):
            self._selected_profile.update(updated_profile)
            self._ui_helper.call(lambda: self._server_card.update_server(self._selected_profile))
