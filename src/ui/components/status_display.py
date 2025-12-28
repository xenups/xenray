"""Status display component for showing connection status below button."""

import flet as ft
from src.ui.helpers.ui_thread_helper import UIThreadHelper

from src.core.i18n import t


class StatusDisplay(ft.Container):
    """
    Displays the connection status below the button.
    Simple layout - just status label.
    """

    def __init__(self):
        super().__init__()

        self._is_connected = False

        # Status Label (initial instance)
        self._status_label = self._create_label(t("app.disconnected"), ft.Colors.ORANGE_400)

        # Animated Switcher for Morphism
        self._switcher = ft.AnimatedSwitcher(
            content=self._status_label,
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=200,
            reverse_duration=200,
            switch_in_curve=ft.AnimationCurve.EASE_OUT,
            switch_out_curve=ft.AnimationCurve.EASE_IN,
        )

        # Main Layout
        self._text_column = ft.Column(
            [
                self._switcher,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

        self.content = ft.Container(
            content=self._text_column,
            padding=ft.padding.symmetric(horizontal=10, vertical=10),
            alignment=ft.Alignment.CENTER,
            width=320,
        )

    def _create_label(self, text: str, color: str) -> ft.Text:
        """Creates a new text instance for the switcher."""
        return ft.Text(
            text,
            size=14,
            weight=ft.FontWeight.W_500,
            color=color,
            text_align=ft.TextAlign.CENTER,
        )

    def _update_label(self, text: str, color: str):
        """Triggers a smooth transition to a new label."""
        self._status_label = self._create_label(text, color)
        self._switcher.content = self._status_label
        if UIThreadHelper.is_mounted(self):
            self.update()

    def set_step(self, msg: str):
        """Updates the status text during connection steps."""
        self._update_label(msg, ft.Colors.AMBER_400)

    def set_status(self, msg: str):
        """Updates status message."""
        self._update_label(msg, ft.Colors.GREY_500)

    def set_initializing(self):
        self._update_label(t("app.initializing"), ft.Colors.AMBER_400)

    def set_connecting(self):
        self._update_label(t("app.connecting"), ft.Colors.AMBER_400)

    def set_connected(self, country_data: dict = None):
        """Sets status to Connected."""
        self._is_connected = True
        self._update_label(t("app.connected"), "#7c3aed")  # Purple

    def set_disconnected(self):
        """Reset to disconnected state."""
        self._is_connected = False
        self._update_label(t("app.disconnected"), ft.Colors.ORANGE_400)

    def set_disconnecting(self):
        """Show disconnecting state."""
        self._is_connected = False
        self._update_label(t("app.disconnecting"), ft.Colors.RED_400)

    def set_pre_connection_ping(self, latency_text: str, is_success: bool):
        """Updates the status text with latency."""
        import re

        status_text = ""
        status_color = ft.Colors.GREY_500

        if latency_text == "...":
            status_text = t("app.checking")
            status_color = ft.Colors.GREY_500
        else:
            has_number = bool(re.search(r"\d+", latency_text))
            prefix = f"{t('connection.ping_prefix')} " if is_success and has_number else ""
            status_text = f"{prefix}{latency_text}"

            if is_success:
                status_color = ft.Colors.GREEN_400
            else:
                status_color = ft.Colors.RED_400

        self._update_label(status_text, status_color)
