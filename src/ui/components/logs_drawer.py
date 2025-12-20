"""Logs drawer component with network stats and i18n support."""

import flet as ft

from src.core.i18n import get_language, t
from src.ui.log_viewer import LogViewer


def to_persian_numerals(text: str) -> str:
    """Convert Latin numerals to Persian numerals."""
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    latin_digits = "0123456789"
    result = text
    for latin, persian in zip(latin_digits, persian_digits):
        result = result.replace(latin, persian)
    return result


class LogsDrawer(ft.NavigationDrawer):
    """Logs drawer component with network stats."""

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

        # Network Stats Row
        self._download_icon = ft.Icon(
            ft.Icons.ARROW_DOWNWARD, size=14, color=ft.Colors.GREEN_400
        )
        self._download_text = ft.Text(
            "0 KB/s",
            size=12,
            color=ft.Colors.GREEN_400,
            weight=ft.FontWeight.W_500,
            width=70,
        )
        self._upload_icon = ft.Icon(
            ft.Icons.ARROW_UPWARD, size=14, color=ft.Colors.BLUE_400
        )
        self._upload_text = ft.Text(
            "0 KB/s",
            size=12,
            color=ft.Colors.BLUE_400,
            weight=ft.FontWeight.W_500,
            width=70,
        )

        self._stats_divider = ft.Container(
            width=1,
            height=14,
            bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE),
        )

        self._stats_row = ft.Row(
            [
                self._download_icon,
                ft.Container(width=4),
                self._download_text,
                ft.Container(width=10),
                self._stats_divider,
                ft.Container(width=10),
                self._upload_icon,
                ft.Container(width=4),
                self._upload_text,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            visible=True,
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
                # Network Stats
                ft.Container(
                    content=self._stats_row,
                    padding=ft.padding.only(bottom=10),
                ),
                ft.Divider(),
                # Logs content
                ft.Container(
                    content=self._log_viewer.control,
                    padding=ft.padding.only(left=15, right=15, bottom=15),
                    expand=True,
                ),
            ],
            bgcolor=ft.Colors.with_opacity(0.9, "#0f172a"),
            shadow_color=ft.Colors.with_opacity(0.2, ft.Colors.BLACK),
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

    def update_network_stats(self, download_speed: str, upload_speed: str):
        """Update network stats elements (Idempotent)."""
        # Only update if values changed to prevent unnecessary repaints
        dl_val = (
            to_persian_numerals(download_speed)
            if get_language() == "fa"
            else download_speed
        )
        ul_val = (
            to_persian_numerals(upload_speed)
            if get_language() == "fa"
            else upload_speed
        )

        changed = False
        if self._download_text.value != dl_val:
            self._download_text.value = dl_val
            changed = True
        if self._upload_text.value != ul_val:
            self._upload_text.value = ul_val
            changed = True

        if changed and self._stats_row.page:
            self._stats_row.update()

    def show_stats(self, visible: bool = True):
        """Control visibility of stats row."""
        if self._stats_row.visible != visible:
            self._stats_row.visible = visible
            if self._stats_row.page:
                self._stats_row.update()
