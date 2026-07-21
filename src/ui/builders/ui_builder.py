"""UI Builder - Constructs main UI layout and components."""
from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from src.ui.components.connection_button import ConnectionButton
from src.ui.components.header import Header
from src.ui.components.server_card import ServerCard
from src.ui.components.status_display import StatusDisplay
from src.ui.theme import AppColors

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class UIBuilder:
    """Builds the main UI layout."""

    def __init__(self, main_window: MainWindow):
        self._main = main_window

    def build_ui(self):
        """Build and configure all UI components."""
        # Header
        self._main._header = Header(
            self._main._page,
            self._main._open_logs_drawer,
            self._main._open_settings_drawer,
        )

        # Heartbeat indicator
        self._main._heartbeat = ft.Container(
            width=8,
            height=8,
            bgcolor=ft.Colors.GREEN_400,
            border_radius=4,
            animate_opacity=1000,
            opacity=0.0,
        )

        # Main components
        self._main._status_display = StatusDisplay()
        self._main._connection_button = ConnectionButton(on_click=self._main._on_connect_clicked)
        self._main._server_card = ServerCard(
            app_context=self._main._app_context, on_click=self._main._open_server_drawer
        )

        # Dashboard view
        self._main._dashboard_view = self._main._create_dashboard_view()

        # View switcher
        self._main._view_switcher = ft.AnimatedSwitcher(
            content=self._main._dashboard_view,
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=200,
            reverse_duration=200,
            switch_in_curve=ft.AnimationCurve.EASE_IN,
            switch_out_curve=ft.AnimationCurve.EASE_OUT,
            expand=True,
        )

        # Background — rich dark gradient
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

        # Horizon glow overlay
        self._main._earth_glow = ft.Container(
            gradient=ft.RadialGradient(
                center=ft.Alignment.BOTTOM_CENTER,
                radius=1.2,
                colors=[
                    ft.Colors.with_opacity(0.0, ft.Colors.TRANSPARENT),
                    ft.Colors.with_opacity(0.0, ft.Colors.TRANSPARENT),
                ],
            ),
            width=1600,
            height=600,
            bottom=-250,
            left=0,
            right=0,
            opacity=0.0,
            animate_opacity=500,
        )

        # Main content — subtle glass panel
        self._main._main_content = ft.Container(
            content=self._main._view_switcher,
            bgcolor=ft.Colors.with_opacity(AppColors.GLASS_BG_OPACITY, ft.Colors.WHITE),
            border=ft.Border.all(0.5, ft.Colors.with_opacity(AppColors.GLASS_BORDER, ft.Colors.WHITE)),
            padding=0,
            expand=True,
        )

        # Stack all layers — fills the native window frame naturally
        self._main._stack = ft.Stack(
            controls=[
                self._main._background,
                self._main._earth_glow,
                self._main._main_content,
            ],
            expand=True,
        )

        # page.add() is called ONCE from main.py — not here

        # Force dark theme
        self._main._page.theme_mode = ft.ThemeMode.DARK
        self._main._connection_button.update_theme(True)
        self._main._server_card.update_theme(True)

        # Window stays hidden — main() will reveal it after full init
        self._main._page.update()
