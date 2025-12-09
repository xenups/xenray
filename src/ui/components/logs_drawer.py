"""Logs drawer component with i18n support."""

import flet as ft

from src.core.i18n import t
from src.ui.log_viewer import LogViewer


class LogsDrawer(ft.NavigationDrawer):
    """Logs drawer component."""

    def __init__(self, log_viewer: LogViewer, heartbeat: ft.Container):
        self._log_viewer = log_viewer
        self._heartbeat = heartbeat
        self._heartbeat.animate_opacity = 500

        self._pause_button = ft.IconButton(
            icon=ft.Icons.PAUSE_ROUNDED,
            tooltip=t("logs.pause"),
            on_click=self._toggle_log_pause,
            icon_color=ft.Colors.RED_600,
        )

        super().__init__(
            controls=[
                # Header
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(
                                t("logs.title"), size=22, weight=ft.FontWeight.BOLD
                            ),
                            ft.Row([self._pause_button, self._heartbeat], spacing=10),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=20,
                ),
                ft.Divider(),
                # Logs content
                ft.Container(
                    content=self._log_viewer.control,
                    padding=ft.padding.only(left=15, right=15, bottom=15),
                    expand=True,
                ),
            ],
            bgcolor=ft.Colors.SURFACE,
        )

    def _toggle_log_pause(self, e: ft.ControlEvent) -> None:
        """Toggle pause state for log updates."""
        is_paused = self._log_viewer.toggle_pause()

        if is_paused:
            self._pause_button.icon = ft.Icons.PLAY_ARROW_ROUNDED
            self._pause_button.tooltip = t("logs.resume")
            self._pause_button.icon_color = ft.Colors.GREEN_600
        else:
            self._pause_button.icon = ft.Icons.PAUSE_ROUNDED
            self._pause_button.tooltip = t("logs.pause")
            self._pause_button.icon_color = ft.Colors.RED_600

        e.control.page.update()
