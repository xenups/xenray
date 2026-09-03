"""Close Confirmation Dialog Component — Apple-style glassmorphism exit/minimize dialog."""

import flet as ft
from loguru import logger

from src.core.i18n import t


class CloseDialog(ft.AlertDialog):
    """Redesigned minimal glass dialog asking user to minimize or exit."""

    def __init__(self, on_exit: callable, on_minimize: callable, app_context):
        self._on_exit_callback = on_exit
        self._on_minimize_callback = on_minimize
        self._app_context = app_context

        # Define checkbox early so the handlers can reference it
        self.remember_checkbox = ft.Checkbox(
            label=t("close_dialog.remember", default="Always minimize to tray"),
            value=False,
            label_style=ft.TextStyle(
                size=12,
                color="#94A3B8",
                weight=ft.FontWeight.W_300,
            ),
            active_color="#A855F7",
            check_color=ft.Colors.WHITE,
        )

        super().__init__(
            modal=True,
            content=self._build_content(),
            shape=ft.RoundedRectangleBorder(radius=18),
            bgcolor=ft.Colors.with_opacity(0.95, "#141023"),
        )

    def _build_content(self):
        try:
            title_text = t("close_dialog.title", default="Exit Application")
            message_text = t(
                "close_dialog.message",
                default="Would you like to minimize XenRay to tray or exit completely?",
            )
            exit_label = t("close_dialog.exit", default="Exit")
            minimize_label = t("close_dialog.minimize", default="Minimize to Tray")
        except Exception:
            title_text = "Exit Application"
            message_text = "Would you like to minimize XenRay to tray or exit completely?"
            exit_label = "Exit"
            minimize_label = "Minimize to Tray"

        header = ft.Text(
            title_text,
            size=16,
            weight=ft.FontWeight.W_300,
            color=ft.Colors.WHITE,
            style=ft.TextStyle(letter_spacing=0.6),
        )

        message = ft.Text(
            message_text,
            size=13,
            weight=ft.FontWeight.W_300,
            color="#94A3B8",
        )

        exit_btn = ft.OutlinedButton(
            content=ft.Text(
                exit_label,
                size=12,
                color="#FCA5A5",
                weight=ft.FontWeight.W_400,
            ),
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.with_opacity(0.15, "#EF4444"),
                side=ft.BorderSide(1.0, ft.Colors.with_opacity(0.40, "#EF4444")),
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            ),
            on_click=self._handle_exit,
        )

        minimize_btn = ft.OutlinedButton(
            content=ft.Text(
                minimize_label,
                size=12,
                color=ft.Colors.WHITE,
                weight=ft.FontWeight.W_400,
            ),
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
                side=ft.BorderSide(1.0, ft.Colors.with_opacity(0.10, ft.Colors.WHITE)),
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            ),
            on_click=self._handle_minimize,
        )

        buttons_row = ft.Row(
            [exit_btn, minimize_btn],
            alignment=ft.MainAxisAlignment.END,
            spacing=10,
        )

        return ft.Container(
            content=ft.Column(
                [
                    header,
                    message,
                    ft.Container(height=4),
                    self.remember_checkbox,
                    ft.Container(height=4),
                    buttons_row,
                ],
                tight=True,
                spacing=10,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            width=340,
        )

    def _handle_exit(self, e):
        logger.debug("[DEBUG] Close dialog: Exit clicked")
        if self.page is not None:
            try:
                self.page.pop_dialog()
            except Exception:
                pass
        self._on_exit_callback()

    def _handle_minimize(self, e):
        logger.debug(f"[DEBUG] Close dialog: Minimize clicked (remember={self.remember_checkbox.value})")
        if self.remember_checkbox.value:
            self._app_context.settings.set_remember_close_choice(True)

        if self.page is not None:
            try:
                self.page.pop_dialog()
            except Exception:
                pass
        self._on_minimize_callback()
