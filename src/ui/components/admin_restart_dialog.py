"""Admin Rights Required Confirmation Dialog Component."""

import flet as ft

from src.utils.platform_utils import Platform, PlatformUtils


class AdminRestartDialog(ft.AlertDialog):
    """Shows an AlertDialog asking the user to restart the app as Admin."""

    def __init__(self, on_restart: callable):
        self._on_restart_callback = on_restart
        platform = PlatformUtils.get_platform()

        # Different content for Linux (can't auto-restart with GUI)
        # Linux now supports pkexec restart
        if platform == Platform.LINUX:
            title_text = "Root Privileges Required"
            content_text = (
                "VPN mode requires root privileges (or capabilities).\n"
                "The application needs to restart with sudo/pkexec.\n\n"
                "Do you want to restart now?"
            )
            actions = [
                ft.TextButton("Cancel", on_click=self._close_dlg),
                ft.TextButton("Restart", on_click=self._confirm_restart),
            ]
        else:
            title_text = "Admin Rights Required"
            content_text = (
                "VPN mode requires Administrator privileges.\n\n"
                "Do you want to restart the application as Admin?"
            )
            actions = [
                ft.TextButton("Cancel", on_click=self._close_dlg),
                ft.TextButton("Restart", on_click=self._confirm_restart),
            ]

        super().__init__(
            modal=True,
            title=ft.Text(title_text),
            content=ft.Text(content_text),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def _close_dlg(self, e):
        self.open = False
        if self.page:
            self.page.update()

    def _confirm_restart(self, e):
        self.open = False
        if self.page:
            self.page.update()
        self._on_restart_callback()
