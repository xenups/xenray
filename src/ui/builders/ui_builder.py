"""UI Builder - Coordinates high-level main shell assembly and component-driven view layout."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from src.core.logger import logger
from src.ui.components.common.header import Header
from src.ui.components.common.nav_sidebar import NavSidebar
from src.ui.components.common.window_title_bar import WindowTitleBar
from src.ui.components.dashboard.connection_button import ConnectionButton
from src.ui.components.dashboard.server_card import ServerCard
from src.ui.components.dashboard.status_display import StatusDisplay
from src.ui.components.lan.lan_sharing_card import LanSharingCard
from src.ui.components.splash_screen import SplashScreen
from src.ui.pages.dashboard_page import DashboardView
from src.ui.pages.logs_page import LogsView
from src.ui.pages.servers_page import ServersView
from src.ui.pages.sni_spoof_page import SniSpoofPage
from src.ui.pages.statistics_page import StatisticsView
from src.ui.theme import AppColors

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class UIBuilder:
    """Component-driven main layout orchestrator assembling the shell and dual-pane views."""

    def __init__(self, main_window: MainWindow):
        self._main = main_window

    def build_core_components(self) -> None:
        """Step 1: Construct core reusable component instances."""
        self._main._lan_sharing_card = LanSharingCard(self._main._app_context)

        self._main._header = Header(
            self._main._page,
            self._main._open_logs_drawer,
            self._main._open_settings_drawer,
            lan_sharing_card=self._main._lan_sharing_card,
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
            app_context=self._main._app_context,
            on_click=self._main._open_server_drawer,
        )

    def build_stitch_views(self) -> None:
        """Step 2: Compose component-driven views and mount the dual-pane application layout."""
        # Guard against double construction (MainWindow init AND the warmup pipeline).
        if getattr(self._main, "_stitch_dashboard_view", None) is not None:
            return

        page = self._main._page

        # 1. Domain view components
        self._main._stitch_dashboard_view = DashboardView(
            on_toggle_click=self._main._on_connect_clicked,
            on_change_server_click=lambda e: self._main._on_nav_tab_changed("servers"),
            on_open_statistics_click=lambda e: self._main._on_nav_tab_changed("statistics"),
            connection_button=self._main._connection_button,
            app_context=self._main._app_context,
            server_card=self._main._server_card,
        )

        self._main._stitch_statistics_view = StatisticsView(
            on_back_click=lambda e: self._main._on_nav_tab_changed("dashboard"),
        )

        self._main._stitch_servers_view = ServersView(
            server_list_component=self._main._server_list,
            on_search_change=self._main._on_server_search,
            on_add_server_click=self._main._open_add_server_dialog,
        )

        # SettingsView via encapsulation (SettingsDrawer factory)
        drawer = self._main._settings_drawer
        self._main._stitch_settings_view = drawer.create_settings_page()

        self._main._stitch_logs_view = LogsView(
            log_text_control=self._main._log_viewer.control,
            on_copy_logs_click=lambda e: self._main._log_viewer.copy_to_clipboard(),
            on_clear_logs_click=lambda e: self._main._log_viewer.clear_logs(),
            on_toggle_tailing=lambda e: self._main._toggle_log_tailing(),
        )

        self._main._stitch_sni_spoof_page = SniSpoofPage(
            app_context=self._main._app_context,
        )

        # Bridge UI toggle events to the SNI spoof lifecycle
        from src.services.sni_spoof.bridge import install_sni_spoof_lifecycle_bridge

        install_sni_spoof_lifecycle_bridge()

        # Determine initial active route
        has_servers = self._has_configured_servers()
        initial_tab = "dashboard" if has_servers else "servers"
        self._main._active_tab = initial_tab

        view_map = {
            "dashboard": self._main._stitch_dashboard_view,
            "statistics": self._main._stitch_statistics_view,
            "servers": self._main._stitch_servers_view,
            "logs": self._main._stitch_logs_view,
            "sni_spoof": self._main._stitch_sni_spoof_page,
            "settings": self._main._stitch_settings_view,
        }
        initial_view = view_map.get(initial_tab, self._main._stitch_dashboard_view)

        # 2. Navigation Sidebar component
        self._main._nav_sidebar = NavSidebar(
            active_tab=initial_tab,
            on_tab_change=self._main._on_nav_tab_changed,
            on_connect_click=self._main._on_connect_clicked,
            on_change_server_click=lambda e: self._main._on_nav_tab_changed("servers"),
            on_lan_click=lambda e: self._main._open_lan_page(),
            allow_lan=self._main._app_context.settings.get_allow_lan(),
            sni_spoof_enabled=(
                self._main._app_context.settings.get_sni_spoof_enabled()
                if hasattr(self._main._app_context, "settings")
                else False
            ),
        )

        # Backward compatibility alias
        self._main._dashboard_view = self._main._stitch_dashboard_view

        # View container for smooth crossfade transitions
        self._main._view_switcher = ft.AnimatedSwitcher(
            content=initial_view,
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=200,
            reverse_duration=200,
            switch_in_curve=ft.AnimationCurve.EASE_IN,
            switch_out_curve=ft.AnimationCurve.EASE_OUT,
            expand=True,
        )

        # 3. Dedicated Window Title Bar component
        title_bar = WindowTitleBar(
            on_minimize=lambda e: self._minimize_window(),
            on_close=lambda e: self._close_window(),
        )

        right_content_column = ft.Column(
            [
                title_bar,
                ft.Container(content=self._main._view_switcher, expand=True),
            ],
            spacing=0,
            expand=True,
        )

        # Dual-Pane layout container: Sidebar (left) + Canvas (right)
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

        # Frameless window background drag area
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
            maximizable=False,
        )

        # 4. Splash screen overlay with self-unmounting cleanup
        def _dismiss_splash_overlay() -> None:
            try:
                splash = self._main._splash_screen
                stack = self._main._stack
                if splash is not None and stack is not None and splash in stack.controls:
                    stack.controls.remove(splash)
            except Exception:
                pass
            try:
                self._main._page.update()
            except Exception:
                pass
            logger.debug("[MainWindow] Splash screen dismissed")

        self._main._splash_screen = SplashScreen(on_dismiss=_dismiss_splash_overlay)

        # Shell stack assembly
        self._main._stack = ft.Stack(
            controls=[
                self._main._background,
                self._main._main_content,
                self._main._splash_screen,
            ],
            expand=True,
        )

        page.theme_mode = ft.ThemeMode.DARK
        self._main._connection_button.update_theme(True)
        self._main._server_card.update_theme(True)

        page.update()

    def build_ui(self) -> None:
        """Build and assemble all UI components."""
        self.build_core_components()
        self.build_stitch_views()

    def _has_configured_servers(self) -> bool:
        """Check if any servers or subscriptions exist for initial route selection."""
        try:
            if hasattr(self._main, "_selected_profile") and self._main._selected_profile:
                return True
            ctx = getattr(self._main, "_app_context", None)
            if ctx:
                profiles = ctx.profiles.load_all() if hasattr(ctx, "profiles") and ctx.profiles else []
                subs = ctx.subscriptions.load_all() if hasattr(ctx, "subscriptions") and ctx.subscriptions else []
                return len(profiles) > 0 or len(subs) > 0
        except Exception:
            pass
        return False

    def _minimize_window(self) -> None:
        page = self._main._page
        if page:
            page.window.minimized = True
            page.update()

    def _close_window(self) -> None:
        if hasattr(self._main, "show_close_dialog"):
            self._main.show_close_dialog()
        elif self._main._page:
            self._main._page.window.close()
