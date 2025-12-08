"""Logs drawer component."""

import flet as ft

from src.ui.log_viewer import LogViewer


class LogsDrawer(ft.NavigationDrawer):
    """Logs drawer component."""

    def __init__(self, log_viewer: LogViewer, heartbeat: ft.Container):
        self._log_viewer = log_viewer
        self._heartbeat = heartbeat
        self._heartbeat.animate_opacity = 500

        # ۱. ساخت دکمه مکث (در LogsDrawer)
        self._pause_button = ft.IconButton(
            icon=ft.Icons.PAUSE_ROUNDED,
            tooltip="مکث به‌روزرسانی لاگ (Pause log update)",
            # این تابع، toggle_pause را در LogViewer فراخوانی می‌کند
            on_click=self._toggle_log_pause,
            icon_color=ft.Colors.RED_600,
        )

        super().__init__(
            controls=[
                # Header with padding
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(
                                "Connection Logs", size=22, weight=ft.FontWeight.BOLD
                            ),
                            # ۲. اضافه کردن دکمه و Heartbeat به Row
                            ft.Row([self._pause_button, self._heartbeat], spacing=10),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=20,
                ),
                ft.Divider(),
                # Logs fill remaining space - single container
                ft.Container(
                    content=self._log_viewer.control,  # استفاده از control اصلاح شده LogViewer
                    padding=ft.padding.only(left=15, right=15, bottom=15),
                    expand=True,
                ),
            ],
            bgcolor=ft.Colors.SURFACE,
        )

    def _toggle_log_pause(self, e: ft.ControlEvent) -> None:
        """
        تغییر وضعیت مکث در LogViewer و آپدیت آیکون دکمه در LogsDrawer.
        """
        # فراخوانی متد toggle_pause که وضعیت جدید را برمی‌گرداند
        is_paused = self._log_viewer.toggle_pause()

        # آپدیت آیکون دکمه بر اساس وضعیت جدید
        if is_paused:
            self._pause_button.icon = ft.Icons.PLAY_ARROW_ROUNDED
            self._pause_button.tooltip = "ادامه به‌روزرسانی لاگ"
            self._pause_button.icon_color = ft.Colors.GREEN_600
        else:
            self._pause_button.icon = ft.Icons.PAUSE_ROUNDED
            self._pause_button.tooltip = "مکث به‌روزرسانی لاگ"
            self._pause_button.icon_color = ft.Colors.RED_600

        # آپدیت UI برای نمایش تغییر آیکون
        e.control.page.update()
