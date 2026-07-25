"""UI Builder - Constructs main UI layout and Stitch-inspired views."""
from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from src.ui.components.connection_button import ConnectionButton
from src.ui.components.header import Header
from src.ui.components.nav_sidebar import NavSidebar
from src.ui.components.server_card import ServerCard
from src.ui.components.settings_sections import ModeSwitchRow
from src.ui.components.status_display import StatusDisplay
from src.ui.theme import AppColors
from src.ui.views.dashboard_view import DashboardView
from src.ui.views.logs_view import LogsView
from src.ui.views.servers_view import ServersView
from src.ui.views.settings_view import SettingsView

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class UIBuilder:
    """Builds the main UI layout and view architecture."""

    def __init__(self, main_window: MainWindow):
        self._main = main_window

    def build_core_components(self):
        """Step 1: Construct core legacy components needed by drawers."""
        self._main._header = Header(
            self._main._page,
            self._main._open_logs_drawer,
            self._main._open_settings_drawer,
        )

        self._main._heartbeat = ft.Container(
            width=8,
            height=8,
            bgcolor=AppColors.PRIMARY,
            border_radius=4,
            animate_opacity=1000,
            opacity=0.0,
        )

        self._main._status_display = StatusDisplay()
        self._main._connection_button = ConnectionButton(on_click=self._main._on_connect_clicked)
        self._main._server_card = ServerCard(
            app_context=self._main._app_context, on_click=self._main._open_server_drawer
        )

    def build_stitch_views(self):
        """Step 2: Construct Stitch views and dual-pane layout after drawers are setup."""
        # Build Stitch Views
        self._main._stitch_dashboard_view = DashboardView(
            on_toggle_click=self._main._on_connect_clicked,
            on_change_server_click=lambda e: self._main._on_nav_tab_changed("servers"),
            connection_button=self._main._connection_button,
        )

        self._main._stitch_servers_view = ServersView(
            server_list_component=self._main._server_list,
            on_search_change=self._main._on_server_search,
            on_add_server_click=self._main._open_add_server_dialog,
        )

        # SettingsView — reuse drawer's component instances (properly wired)
        drawer = self._main._settings_drawer
        self._main._stitch_settings_view = SettingsView(
            mode_switch_row=ModeSwitchRow(
                drawer._is_proxy,
                drawer._handle_mode_change,
            ),
            tun_engine_row=drawer._tun_engine_row,
            port_row=drawer._port_row,
            country_row=drawer._country_row,
            language_row=drawer._language_row,
            reconnect_row=drawer._auto_reconnect_row,
            startup_row=drawer._startup_row,
            on_check_update_click=drawer._check_app_updates,
            on_open_routing_click=drawer._open_routing_manager,
            on_open_dns_click=drawer._open_dns_manager,
        )

        self._main._stitch_logs_view = LogsView(
            log_text_control=self._main._log_viewer.control,
            on_copy_logs_click=lambda e: self._main._log_viewer.copy_to_clipboard(),
            on_download_logs_click=lambda e: self._main._log_viewer.export_logs(),
            on_clear_logs_click=lambda e: self._main._log_viewer.clear_logs(),
        )

        # Left Sidebar Navigation
        self._main._nav_sidebar = NavSidebar(
            active_tab="dashboard",
            on_tab_change=self._main._on_nav_tab_changed,
            on_connect_click=self._main._on_connect_clicked,
        )

        # Legacy dashboard view fallback
        self._main._dashboard_view = self._main._stitch_dashboard_view

        # View switcher for main right canvas
        self._main._view_switcher = ft.AnimatedSwitcher(
            content=self._main._stitch_dashboard_view,
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=200,
            reverse_duration=200,
            switch_in_curve=ft.AnimationCurve.EASE_IN,
            switch_out_curve=ft.AnimationCurve.EASE_OUT,
            expand=True,
        )

        # Background — deep gradient (v0.1.7-beta style)
        self._main._background = ft.Container(
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[
                    AppColors.BACKGROUND_GRADIENT_START,
                    AppColors.BACKGROUND_GRADIENT_CENTER,
                    AppColors.BACKGROUND_GRADIENT_END,
                ],
            ),
            expand=True,
        )

        # Dual-Pane layout container: Left Sidebar + Right Content Canvas
        self._main._main_content = ft.Container(
            content=ft.Row(
                [
                    self._main._nav_sidebar,
                    ft.Container(
                        content=self._main._view_switcher,
                        expand=True,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            expand=True,
        )

        # Stack all layers
        self._main._stack = ft.Stack(
            controls=[
                self._main._background,
                self._main._main_content,
            ],
            expand=True,
        )

        # Force dark theme
        self._main._page.theme_mode = ft.ThemeMode.DARK
        self._main._connection_button.update_theme(True)
        self._main._server_card.update_theme(True)

        self._main._page.update()

    def build_ui(self):
        """Build and configure all UI components."""
        self.build_core_components()
        self.build_stitch_views()
