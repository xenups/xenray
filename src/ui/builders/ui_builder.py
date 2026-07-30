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
from src.ui.views.statistics_view import StatisticsView

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
        self._main._connection_button = ConnectionButton(
            on_click=self._main._on_connect_clicked
        )
        self._main._server_card = ServerCard(
            app_context=self._main._app_context, on_click=self._main._open_server_drawer
        )

    def build_stitch_views(self):
        """Step 2: Construct Stitch views and dual-pane layout after drawers are setup."""
        page = self._main._page

        # Build Stitch Views
        self._main._stitch_dashboard_view = DashboardView(
            on_toggle_click=self._main._on_connect_clicked,
            on_change_server_click=lambda e: self._main._on_nav_tab_changed("servers"),
            on_open_statistics_click=lambda e: self._main._on_nav_tab_changed(
                "statistics"
            ),
            connection_button=self._main._connection_button,
        )

        self._main._stitch_statistics_view = StatisticsView(
            on_back_click=lambda e: self._main._on_nav_tab_changed("dashboard"),
        )

        self._main._stitch_servers_view = ServersView(
            server_list_component=self._main._server_list,
            on_search_change=self._main._on_server_search,
            on_add_server_click=self._main._open_add_server_dialog,
        )

        # SettingsView — reuse drawer's component instances
        drawer = self._main._settings_drawer
        is_proxy = drawer._mode_switch_row.value
        self._main._stitch_settings_view = SettingsView(
            mode_switch_row=ModeSwitchRow(
                is_proxy,
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
            on_change_server_click=lambda e: self._main._on_nav_tab_changed("servers"),
        )

        # Legacy dashboard view fallback
        self._main._dashboard_view = self._main._stitch_dashboard_view

        # View container for main right canvas (instant swap, no animation lag)
        self._main._view_switcher = ft.Container(
            content=self._main._stitch_dashboard_view,
            expand=True,
        )

        # Background — deep gradient with WindowDragArea for frameless window movement
        self._main._background = ft.WindowDragArea(
            content=ft.Container(
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
            ),
            expand=True,
        )

        # Top Header Drag Bar with Window Control Buttons
        top_header_bar = ft.Container(
            content=ft.WindowDragArea(
                content=ft.Row(
                    [
                        ft.Container(expand=True),
                        ft.Row(
                            [
                                ft.IconButton(
                                    icon=ft.Icons.MINIMIZE_ROUNDED,
                                    icon_size=14,
                                    icon_color=ft.Colors.with_opacity(
                                        0.65, ft.Colors.WHITE
                                    ),
                                    tooltip="Minimize",
                                    on_click=lambda e: self._handle_window_minimize(),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.CROP_SQUARE_ROUNDED,
                                    icon_size=13,
                                    icon_color=ft.Colors.with_opacity(
                                        0.65, ft.Colors.WHITE
                                    ),
                                    tooltip="Maximize / Restore",
                                    on_click=lambda e: self._handle_window_maximize(),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.CLOSE_ROUNDED,
                                    icon_size=14,
                                    icon_color=ft.Colors.with_opacity(0.8, "#f43f5e"),
                                    tooltip="Close",
                                    on_click=lambda e: self._handle_window_close(),
                                ),
                            ],
                            spacing=2,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
            ),
            height=32,
            padding=ft.Padding.only(right=8, left=12),
        )

        # Right content column with top drag header bar & view switcher
        right_content_column = ft.Column(
            [
                top_header_bar,
                ft.Container(
                    content=self._main._view_switcher,
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        )

        # Dual-Pane layout container: Full-Height Left Sidebar + Right Content Canvas
        self._main._main_content = ft.Container(
            content=ft.Row(
                [
                    self._main._nav_sidebar,
                    right_content_column,
                ],
                spacing=0,
                expand=True,
            ),
            expand=True,
        )

        self._main._stack = ft.Stack(
            controls=[
                self._main._background,
                self._main._main_content,
            ],
            expand=True,
        )

        page.theme_mode = ft.ThemeMode.DARK
        self._main._connection_button.update_theme(True)
        self._main._server_card.update_theme(True)

        page.update()

    def build_ui(self):
        """Build and configure all UI components."""
        self.build_core_components()
        self.build_stitch_views()

    def _handle_window_minimize(self):
        page = self._main._page
        page.window.minimized = True
        page.update()

    def _handle_window_maximize(self):
        page = self._main._page
        is_max = getattr(page.window, "maximized", False)
        page.window.maximized = not is_max
        page.update()

    def _handle_window_close(self):
        page = self._main._page
        if hasattr(self._main, "show_close_dialog"):
            self._main.show_close_dialog()
        else:
            page.window.close()
