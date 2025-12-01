"""Logs drawer component."""

import flet as ft

from src.ui.log_viewer import LogViewer


class LogsDrawer(ft.UserControl):
    """Logs drawer component."""

    def __init__(self, log_viewer: LogViewer, heartbeat: ft.Container):
        super().__init__()
        self._log_viewer = log_viewer
        self._heartbeat = heartbeat

    def build(self):
        return ft.NavigationDrawer(
            controls=[
                # Header with padding
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(
                                "Connection Logs", size=22, weight=ft.FontWeight.BOLD
                            ),
                            self._heartbeat,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=20,
                ),
                ft.Divider(),
                # Logs fill remaining space - single container
                ft.Container(
                    content=self._log_viewer.control,
                    padding=ft.padding.only(left=15, right=15, bottom=15),
                    expand=True,  # This makes it fill remaining vertical space
                ),
            ],
            bgcolor=ft.colors.SURFACE,
        )
