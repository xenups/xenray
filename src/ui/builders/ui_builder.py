"""UI Builder - Constructs main UI layout and Stitch-inspired views."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from src.core.i18n import t
from src.core.logger import logger
from src.ui.components.common.header import Header
from src.ui.components.common.nav_sidebar import NavSidebar
from src.ui.components.dashboard.connection_button import ConnectionButton
from src.ui.components.dashboard.server_card import ServerCard
from src.ui.components.dashboard.status_display import StatusDisplay
from src.ui.components.lan.lan_sharing_card import LanSharingCard
from src.ui.components.settings import ModeSwitchRow
from src.ui.pages.dashboard_page import DashboardView
from src.ui.pages.logs_page import LogsView
from src.ui.pages.servers_page import ServersView
from src.ui.pages.settings_page import SettingsView
from src.ui.pages.statistics_page import StatisticsView
from src.ui.theme import AppColors
from src.ui.views.sni_spoof_view import SniSpoofView

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class UIBuilder:
    """Builds the main UI layout and view architecture."""

    def __init__(self, main_window: MainWindow):
        self._main = main_window

    def build_core_components(self):
        """Step 1: Construct core legacy components needed by drawers."""
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
        self._main._connection_button = ConnectionButton(
            on_click=self._main._on_connect_clicked
        )
        self._main._server_card = ServerCard(
            app_context=self._main._app_context, on_click=self._main._open_server_drawer
        )

    def create_dashboard_view(self) -> ft.Column:
        """Create centerpiece column layout for dashboard view."""
        if not self._main._lan_sharing_card:
            self._main._lan_sharing_card = LanSharingCard(self._main._app_context)

        center_block = ft.Container(
            content=ft.Column(
                [self._main._connection_button, self._main._status_display],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=0,
            ),
            margin=ft.Margin.only(top=20),
        )

        return ft.Column(
            [
                self._main._header,
                ft.Container(expand=True),
                center_block,
                ft.Container(expand=True),
                self._main._server_card,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.START,
            expand=True,
        )

    def _toggle_log_tailing(self):
        """Toggle log tailing on/off via the shared LogViewer (Start/Stop button on the Logs tab)."""
        try:
            lv = self._main._log_viewer
            if lv is None:
                return
            if getattr(lv, "user_enabled", False):
                lv.stop_tailing()
                lv.user_enabled = False
            else:
                # Start tailing the currently selected source (default: app logs)
                from src.ui.components.logs.logs_drawer import LOG_SOURCES

                lv.user_enabled = True
                lv.start_tailing(*LOG_SOURCES["app"][1])
        except Exception:
            pass

    def build_stitch_views(self):
        """Step 2: Construct Stitch views and dual-pane layout after drawers are setup."""
        # Guard against double construction (MainWindow init AND the warmup
        # pipeline). Rebuilding creates a SECOND _view_switcher / views that are
        # never mounted — breaking tab rendering after the splash.
        if getattr(self._main, "_stitch_dashboard_view", None) is not None:
            return

        page = self._main._page

        # Build Stitch Views
        self._main._stitch_dashboard_view = DashboardView(
            on_toggle_click=self._main._on_connect_clicked,
            on_change_server_click=lambda e: self._main._on_nav_tab_changed("servers"),
            on_open_statistics_click=lambda e: self._main._on_nav_tab_changed(
                "statistics"
            ),
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

        # SettingsView — reuse drawer's component instances
        drawer = self._main._settings_drawer
        connectivity = drawer._connectivity_section
        is_proxy = connectivity.mode_switch_row.value
        self._main._stitch_settings_view = SettingsView(
            mode_switch_row=ModeSwitchRow(
                is_proxy,
                drawer._on_mode_change,
            ),
            tun_engine_row=connectivity.tun_dropdown_row,
            port_row=connectivity.port_row,
            country_row=connectivity.country_row,
            language_row=drawer._language_row,
            reconnect_row=drawer._auto_reconnect_row,
            startup_row=drawer._startup_row,
            on_check_update_click=drawer._handler.check_app_updates,
            settings_controller=getattr(drawer, "_settings_controller", None),
            on_open_routing_click=drawer._handler.open_routing_manager,
            on_open_dns_click=drawer._handler.open_dns_manager,
            lan_share_row=getattr(drawer, "_lan_share_row", None),
            http_port_row=connectivity.http_port_row,
        )

        self._main._stitch_logs_view = LogsView(
            log_text_control=self._main._log_viewer.control,
            on_copy_logs_click=lambda e: self._main._log_viewer.copy_to_clipboard(),
            on_clear_logs_click=lambda e: self._main._log_viewer.clear_logs(),
            on_toggle_tailing=lambda e: self._toggle_log_tailing(),
        )

        self._main._stitch_sni_spoof_view = SniSpoofView(
            app_context=self._main._app_context,
        )

        # Bridge UI toggle events (TOPIC_SNI_SPOOF_CHANGED) to the shared
        # SniSpoofService so the switch starts/stops the real listener, and
        # keeps the listener from running outside an active connection.
        from src.services.sni_spoof.bridge import install_sni_spoof_lifecycle_bridge

        install_sni_spoof_lifecycle_bridge()

        # Check if server profiles or subscriptions exist on startup — default to Dashboard if servers exist
        has_servers = False
        try:
            if (
                hasattr(self._main, "_selected_profile")
                and self._main._selected_profile
            ):
                has_servers = True
            elif hasattr(self._main, "_app_context") and self._main._app_context:
                ctx = self._main._app_context
                profiles = (
                    ctx.profiles.load_all()
                    if hasattr(ctx, "profiles") and ctx.profiles
                    else []
                )
                subs = (
                    ctx.subscriptions.load_all()
                    if hasattr(ctx, "subscriptions") and ctx.subscriptions
                    else []
                )
                has_servers = len(profiles) > 0 or len(subs) > 0
        except Exception:
            pass

        initial_tab = "dashboard" if has_servers else "servers"
        self._main._active_tab = initial_tab

        view_map = {
            "dashboard": self._main._stitch_dashboard_view,
            "statistics": self._main._stitch_statistics_view,
            "servers": self._main._stitch_servers_view,
            "logs": self._main._stitch_logs_view,
            "sni_spoof": self._main._stitch_sni_spoof_view,
            "settings": self._main._stitch_settings_view,
        }
        initial_view = view_map.get(initial_tab, self._main._stitch_dashboard_view)

        # Left Sidebar Navigation
        self._main._nav_sidebar = NavSidebar(
            active_tab=initial_tab,
            on_tab_change=self._main._on_nav_tab_changed,
            on_connect_click=self._main._on_connect_clicked,
            on_change_server_click=lambda e: self._main._on_nav_tab_changed("servers"),
            on_lan_click=lambda e: self._main._open_lan_page(),
            allow_lan=self._main._app_context.settings.get_allow_lan(),
        )

        # Legacy dashboard view fallback
        self._main._dashboard_view = self._main._stitch_dashboard_view

        # View container for main right canvas (smooth 200ms crossfade transitions)
        self._main._view_switcher = ft.AnimatedSwitcher(
            content=initial_view,
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=200,
            reverse_duration=200,
            switch_in_curve=ft.AnimationCurve.EASE_IN,
            switch_out_curve=ft.AnimationCurve.EASE_OUT,
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

        from src.core.constants import APP_VERSION

        # Top Header Drag Bar with App Branding (Left) and Window Control Buttons (Right)
        header_branding = ft.Row(
            [
                ft.Image(
                    src="icon.png",
                    width=20,
                    height=20,
                    fit="contain",
                ),
                ft.Text(
                    "XenRay",
                    size=14,
                    weight=ft.FontWeight.W_800,
                    color=ft.Colors.WHITE,
                ),
                ft.Container(
                    content=ft.Text(
                        f"v{APP_VERSION}",
                        size=10,
                        color="#8A8F9E",
                    ),
                    margin=ft.Margin.only(top=4),
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        top_header_bar = ft.Container(
            content=ft.WindowDragArea(
                content=ft.Row(
                    [
                        header_branding,
                        ft.Row(
                            [
                                ft.IconButton(
                                    icon=ft.Icons.MINIMIZE_ROUNDED,
                                    icon_size=14,
                                    icon_color=ft.Colors.with_opacity(
                                        0.65, ft.Colors.WHITE
                                    ),
                                    tooltip=t("window.minimize"),
                                    on_click=lambda e: self._handle_window_minimize(),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.CLOSE_ROUNDED,
                                    icon_size=14,
                                    icon_color=ft.Colors.with_opacity(0.8, "#f43f5e"),
                                    tooltip=t("window.close"),
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
            height=36,
            padding=ft.Padding.only(right=8, left=14, top=4),
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

        # Drag area wraps the background — sits at the bottom of the Stack so all
        # interactive controls on upper layers still receive their own events.
        # Dragging any empty space in the window moves the window.
        _drag_bg = ft.WindowDragArea(
            content=self._main._background,
            expand=True,
            maximizable=False,
        )

        from src.ui.components.splash_screen import SplashScreen

        def _dismiss_splash_overlay() -> None:
            """Properly unmount the splash overlay and repaint the page.

            Removing the control from the stack (instead of merely toggling
            visibility) prevents a transparent overlay from trapping focus and
            freezing the main window until the user minimizes/restores.
            """
            try:
                splash = self._main._splash_screen
                stack = self._main._stack
                if (
                    splash is not None
                    and stack is not None
                    and splash in stack.controls
                ):
                    stack.controls.remove(splash)
            except Exception:
                pass
            try:
                self._main._page.update()
            except Exception:
                pass
            logger.debug("[MainWindow] Splash screen dismissed")

        self._main._splash_screen = SplashScreen(on_dismiss=_dismiss_splash_overlay)

        self._main._stack = ft.Stack(
            controls=[
                _drag_bg,
                self._main._main_content,
                self._main._splash_screen,
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
