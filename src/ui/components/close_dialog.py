"""Close Confirmation Dialog Component."""

import os
import flet as ft
from loguru import logger
from src.core.i18n import t


class CloseDialog(ft.AlertDialog):
    """Redesigned premium dialog asking user to minimize or exit."""

    def __init__(self, on_exit: callable, on_minimize: callable, config_manager):
        self._on_exit_callback = on_exit
        self._on_minimize_callback = on_minimize
        self._config_manager = config_manager

        # Define checkbox early so the handlers can reference it
        self.remember_checkbox = ft.Checkbox(
            label=t("close_dialog.remember"),
            value=False,
            label_style=ft.TextStyle(size=13, color=ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE)),
            # White inside when empty, blue accent checkmark
            fill_color={
                ft.ControlState.SELECTED: ft.Colors.BLUE_ACCENT,
                ft.ControlState.DEFAULT: ft.Colors.WHITE,
            },
            check_color=ft.Colors.WHITE,
        )

        super().__init__(
            modal=True,
            content=self._build_content(),
            shape=ft.RoundedRectangleBorder(radius=15),
            bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.SURFACE),
        )

    def _build_content(self):
        try:
            title_text = t("close_dialog.title")
            message_text = t("close_dialog.message")
            exit_label = t("close_dialog.exit")
            minimize_label = t("close_dialog.minimize")
        except Exception:
            title_text, message_text = "Exit", "Exit or Minimize?"
            exit_label, minimize_label = "Exit", "Minimize"

        return ft.Container(
            content=ft.Column(
                [
                    # Header
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.EXIT_TO_APP_ROUNDED,
                                color=ft.Colors.BLUE_ACCENT,
                                size=28,
                            ),
                            ft.Text(title_text, size=18, weight=ft.FontWeight.BOLD),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        spacing=10,
                    ),
                    # Message
                    ft.Text(message_text, size=14, opacity=0.9),
                    ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                    # Buttons Row (Moved into content for precise placement)
                    ft.Row(
                        [
                            ft.TextButton(
                                exit_label,
                                on_click=self._handle_exit,
                                icon=ft.Icons.POWER_SETTINGS_NEW,
                                icon_color=ft.Colors.RED_ACCENT,
                                style=ft.ButtonStyle(color=ft.Colors.RED_ACCENT),
                            ),
                            ft.ElevatedButton(
                                minimize_label,
                                on_click=self._handle_minimize,
                                icon=ft.Icons.MINIMIZE,
                                style=ft.ButtonStyle(
                                    bgcolor=ft.Colors.BLUE_ACCENT,
                                    color=ft.Colors.WHITE,
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        spacing=10,
                    ),
                    # Checkbox (Under the buttons)
                    ft.Container(
                        content=self.remember_checkbox,
                        margin=ft.margin.only(top=5),
                    ),
                ],
                tight=True,
                spacing=10,
            ),
            padding=10,
            width=320,
        )

    def _handle_exit(self, e):
        logger.debug("[DEBUG] Close dialog: Exit clicked")
        self.open = False
        if self.page:
            self.page.update()
        self._on_exit_callback()

    def _handle_minimize(self, e):
        logger.debug(f"[DEBUG] Close dialog: Minimize clicked (remember={self.remember_checkbox.value})")
        if self.remember_checkbox.value:
            self._config_manager.set_remember_close_choice(True)

        self.open = False
        if self.page:
            self.page.update()
        self._on_minimize_callback()
