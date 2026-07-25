"""Main Window module - Root application layout and navigation shell."""

from __future__ import annotations

from typing import Optional

import flet as ft
from loguru import logger

from src.core.app_context import AppContext
from src.core.i18n import t
from src.core.types import ConnectionMode
from src.ui.builders.ui_builder import UIBuilder
from src.ui.components.connection_button import ConnectionButton
from src.ui.components.header import Header
from src.ui.components.nav_sidebar import NavSidebar
from src.ui.components.server_card import ServerCard
from src.ui.components.server_list_item import ServerListItem
from src.ui.components.status_display import StatusDisplay
from src.ui.components.toast import ToastManager
from src.ui.handlers.background_task_handler import BackgroundTaskHandler
from src.ui.handlers.connection_handler import ConnectionHandler
from src.ui.handlers.installer_handler import InstallerHandler
from src.ui.handlers.latency_monitor_handler import LatencyMonitorHandler
from src.ui.handlers.network_stats_handler import NetworkStatsHandler
from src.ui.handlers.reconnect_event_handler import ReconnectEventHandler
from src.ui.handlers.systray_handler import SystrayHandler
from src.ui.handlers.theme_handler import ThemeHandler
from src.ui.helpers.profile_presenter import ProfilePresenter
from src.ui.helpers.ui_thread_helper import UIThreadHelper
from src.ui.helpers.window_state_manager import WindowStateManager
from src.ui.managers.drawer_manager import DrawerManager
from src.ui.managers.monitoring_service import MonitoringService
from src.ui.managers.profile_manager import ProfileManager
from src.ui.server_list import ServerList
from src.ui.views.dashboard_view import DashboardView
from src.ui.views.logs_view import LogsView
from src.ui.views.settings_view import SettingsView
from src.utils.process_utils import ProcessUtils


class MainWindow:
    """Main Application Window."""

    def __init__(
        self,
        page: ft.Page,
        app_context: AppContext,
        latency_monitor_handler: LatencyMonitorHandler,
        connection_handler: ConnectionHandler,
        theme_handler: ThemeHandler,
        installer_handler: InstallerHandler,
        background_task_handler: BackgroundTaskHandler,
        systray_handler: SystrayHandler,
        reconnect_event_handler: ReconnectEventHandler,
        network_stats_handler: NetworkStatsHandler,
        monitoring_service: MonitoringService,
        profile_manager: ProfileManager,
        connection_manager=None,
        network_stats=None,
    ):
        self._page = page
        self._page._main_window = self
        self._app_context = app_context
        self._latency_monitor_handler = latency_monitor_handler
        self._connection_handler = connection_handler
        self._theme_handler = theme_handler
        self._installer_handler = installer_handler
        self._background_task_handler = background_task_handler
        self._systray = systray_handler
        self._reconnect_event_handler = reconnect_event_handler
        self._network_stats_handler = network_stats_handler

        self._ui_helper = UIThreadHelper(page)

        self._current_mode = ConnectionMode.VPN
        self._is_running = False
        self._connecting = False
        self._disconnecting = False
        self._selected_profile: Optional[dict] = None
        self._current_exit_ip: Optional[str] = None

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
        self._log_viewer = None
        self._logs_heartbeat = None

        self._drawer_manager = DrawerManager(self)
        self._ui_builder = UIBuilder(self)

        self._define_callbacks()
        self._current_mode = WindowStateManager.setup_page(self._page, self._app_context)

        self._toast = ToastManager(self._page)
        self._page._toast_manager = self._toast

        self._profile_manager = profile_manager
        self._profile_manager.setup(ui_updater=self._ui_helper.call)
        self._profile_manager.set_ui_update_callback(self._update_selected_profile_ui)

        self._monitoring_service = monitoring_service
        self._monitoring_service.setup(
            ui_updater=self._ui_helper.call,
            toast_manager=self._toast,
        )

        self._ui_builder.build_core_components()
        self._drawer_manager.setup_drawers()
        self._ui_builder.build_stitch_views()

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
            profile_manager_is_running_setter=self._set_profile_manager_running,
            monitoring_service_is_running_setter=self._set_monitoring_service_running,
            update_horizon_glow_callback=lambda s: None,
            main_window=self,
            disconnecting_setter=self._set_disconnecting,
        )

        self._reconnect_event_handler.setup(
            ui_helper=self._ui_helper,
            toast=self._toast,
            status_display=self._status_display,
            connection_button=self._connection_button,
            systray=self._systray,
            update_horizon_glow_callback=lambda s: None,
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
            earth_glow=None,
            logs_heartbeat=self._logs_heartbeat,
            heartbeat=self._heartbeat,
            is_running_getter=lambda: self._is_running,
        )

        self._background_task_handler.setup(page=self._page)
        self._systray.setup(self)
        self._background_task_handler.start()

        self._restore_last_selected_profile()

    def _set_is_running(self, val: bool):
        self._is_running = val
        if hasattr(self, "_stitch_dashboard_view") and self._stitch_dashboard_view:
            self._stitch_dashboard_view.set_connection_state(val, False)
        if hasattr(self, "_nav_sidebar") and self._nav_sidebar:
            self._nav_sidebar.update_connect_button_text(
                t("nav.disconnect", default="Disconnect") if val else t("nav.connect_now", default="Connect Now"),
                val,
                server_name=self._get_sidebar_server_label(),
            )

    def _set_connecting(self, val: bool):
        self._connecting = val
        if hasattr(self, "_stitch_dashboard_view") and self._stitch_dashboard_view:
            self._stitch_dashboard_view.set_connection_state(self._is_running, is_connecting=val, is_disconnecting=self._disconnecting)

    def _set_disconnecting(self, val: bool):
        self._disconnecting = val
        if hasattr(self, "_stitch_dashboard_view") and self._stitch_dashboard_view:
            self._stitch_dashboard_view.set_connection_state(self._is_running, is_connecting=self._connecting, is_disconnecting=val)

    def _set_profile_manager_running(self, val: bool):
        self._profile_manager.is_running = val

    def _set_monitoring_service_running(self, val: bool):
        self._monitoring_service.is_running = val

    def _on_nav_tab_changed(self, tab_id: str):
        if hasattr(self, "_nav_sidebar") and self._nav_sidebar:
            self._nav_sidebar.set_active_tab(tab_id)

        if tab_id == "dashboard" and hasattr(self, "_stitch_dashboard_view"):
            self.navigate_to(self._stitch_dashboard_view)
            if hasattr(self, "_network_stats_handler") and self._network_stats_handler:
                self._network_stats_handler.update_ui_immediately()
        elif tab_id == "servers" and hasattr(self, "_stitch_servers_view"):
            self.navigate_to(self._stitch_servers_view)
        elif tab_id == "logs" and hasattr(self, "_stitch_logs_view"):
            self.navigate_to(self._stitch_logs_view)
        elif tab_id == "settings" and hasattr(self, "_stitch_settings_view"):
            self.navigate_to(self._stitch_settings_view)

    def _get_sidebar_server_label(self) -> str:
        if not self._selected_profile:
            return t("dashboard.no_server", default="No Server")
        name = self._selected_profile.get("name", "Server")
        code = self._selected_profile.get("country_code", "")
        return f"{name} ({code.upper()})" if code else name

    def navigate_to(self, view_control: ft.Control):
        if hasattr(self, "_view_switcher") and self._view_switcher:
            self._view_switcher.content = view_control
            try:
                if self._view_switcher.page:
                    self._view_switcher.update()
            except Exception:
                pass

    def navigate_back(self):
        if hasattr(self, "_stitch_dashboard_view") and self._stitch_dashboard_view:
            self.navigate_to(self._stitch_dashboard_view)

    def set_step(self, step_text: str):
        """Forward micro-state step to DashboardView and StatusDisplay."""
        if hasattr(self, "_stitch_dashboard_view") and self._stitch_dashboard_view:
            self._stitch_dashboard_view.set_step(step_text)
        if hasattr(self, "_status_display") and self._status_display:
            self._status_display.set_step(step_text)

    def _define_callbacks(self):
        self._on_connect_clicked = self._on_connect_clicked_impl
        self._open_server_drawer = self._open_server_drawer_impl
        self._open_logs_drawer = self._open_logs_drawer_impl
        self._open_settings_drawer = self._open_settings_drawer_impl

    def _restore_last_selected_profile(self):
        profile = WindowStateManager.get_initial_selected_profile(self._app_context)
        if profile:
            self._selected_profile = profile
            if hasattr(self, "_server_card") and self._server_card:
                self._update_selected_profile_ui(profile)

    def _restore_from_tray(self):
        """Restore main application window from system tray (thread-safe)."""
        def _restore():
            try:
                if self._page and hasattr(self._page, "window"):
                    self._page.window.minimized = False
                    self._page.window.visible = True
                    self._page.window.focus()
                    try:
                        self._page.update()
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"[MainWindow] Error restoring window from tray: {e}")

        _restore()
        if hasattr(self, "_ui_helper") and self._ui_helper and self._ui_helper._page:
            self._ui_helper.call(_restore)

    restore_from_tray = _restore_from_tray

    def _on_connect_clicked_impl(self, e=None):
        from src.core.connection_fsm import ConnectionState

        fsm_state = self._connection_handler.fsm.state
        if fsm_state in (ConnectionState.CONNECTED, ConnectionState.CONNECTING):
            self._connection_handler.disconnect()
        elif fsm_state in (ConnectionState.DISCONNECTED, ConnectionState.ERROR):
            self._connection_handler.connect_async()

    def _open_server_drawer_impl(self, e=None):
        self._drawer_manager.open_server_sheet(e)

    async def _open_logs_drawer_impl(self, e=None):
        await self._drawer_manager.open_logs_drawer(e)

    async def _open_settings_drawer_impl(self, e=None):
        await self._drawer_manager.open_settings_drawer(e)

    def _extract_profile_info(self, profile: dict) -> dict:
        return ProfilePresenter.extract_profile_info(profile)

    def _update_selected_profile_ui(self, profile: dict):
        self._selected_profile = profile
        self._server_card.update_server(profile)
        profile_info = self._extract_profile_info(profile)
        name = profile.get("name", "Unknown Server") if profile else "No Server Selected"
        latency = profile_info.get("latency", "--")

        if self._is_running or self._connecting:
            server_ip = self._current_exit_ip or profile_info.get("server_ip", "--")
        else:
            server_ip = profile_info.get("server_ip", "--")

        protocol = profile_info.get("protocol", "Xray / VLESS")
        encryption = profile_info.get("encryption", "none")
        country_code = profile_info.get("country_code", "")
        country_name = profile_info.get("country_name", "")

        if hasattr(self, "_stitch_dashboard_view") and self._stitch_dashboard_view:
            self._stitch_dashboard_view.update_server_info(
                name, latency, protocol, encryption, server_ip, country_code, country_name
            )

        if hasattr(self, "_stitch_servers_view") and self._stitch_servers_view:
            self._stitch_servers_view.update_hero_node(name, latency, protocol, "", country_code)

        if hasattr(self, "_nav_sidebar") and self._nav_sidebar:
            label = f"{name} ({country_code.upper()})" if country_code else name
            self._nav_sidebar.update_connect_button_text(
                t("nav.disconnect", default="Disconnect")
                if self._is_running
                else t("nav.connect_now", default="Connect Now"),
                self._is_running,
                server_name=label,
            )

    def _on_server_selected(self, profile: dict):
        self._selected_profile = profile
        self._app_context.settings.set_last_selected_profile_id(profile.get("id"))
        self._update_selected_profile_ui(profile)
        self._connection_handler.reconnect()

    def _on_server_search(self, query: str = ""):
        if hasattr(self, "_server_list") and self._server_list:
            self._server_list.filter_servers(query)

    def _open_add_server_dialog(self, e=None):
        if hasattr(self, "_server_list") and self._server_list:
            self._server_list._show_add_profile_dialog(e)

    def _reset_ui_disconnected(self):
        self._current_exit_ip = None
        self._connection_handler.reset_ui_disconnected()

    def _toggle_theme(self, e=None):
        self._theme_handler.toggle_theme(e)

    def _show_toast(self, message: str, message_type: str = "info"):
        if self._toast:
            self._toast.show(message, message_type)

    def _run_specific_installer(self, component: str):
        self._installer_handler.run_specific_installer(component)

    def _on_profile_updated(self, updated_profile: dict):
        if not self._selected_profile:
            return
        if updated_profile.get("id") == self._selected_profile.get("id"):
            self._selected_profile.update(updated_profile)
            self._ui_helper.call(lambda: self._server_card.update_server(self._selected_profile))

    def _on_mode_changed(self, mode: ConnectionMode):
        if mode == ConnectionMode.VPN and not ProcessUtils.is_admin():
            self._show_toast(t("status.admin_required"), "warning")
            return
        self._current_mode = mode
        self._app_context.settings.set_connection_mode("vpn" if mode == ConnectionMode.VPN else "proxy")
        if self._is_running:
            self._connection_handler.reconnect()
