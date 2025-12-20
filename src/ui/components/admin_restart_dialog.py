"""Admin Rights Required Confirmation Dialog Component."""

import flet as ft


class AdminRestartDialog(ft.AlertDialog):
    """Shows an AlertDialog asking the user to restart the app as Admin."""

    def __init__(self, on_restart: callable):
        self._on_restart_callback = on_restart

        super().__init__(
            modal=True,
            title=ft.Text("Admin Rights Required"),
            content=ft.Text(
                "VPN mode requires Administrator privileges.\n\nDo you want to restart the application as Admin?"
            ),
            actions=[
                ft.TextButton("Cancel", on_click=self._close_dlg),
                ft.TextButton("Restart", on_click=self._confirm_restart),
            ],
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
