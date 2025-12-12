"""Status display component for showing connection status."""

import threading

import flet as ft

from src.core.i18n import t


class StatusDisplay(ft.Container):
    """
    Displays the current connection status and country information.
    Layout: Center(TextColumn)
    """

    def __init__(self):
        super().__init__()

        # --- Controls ---

        # 1. Country/City Name - larger, smoother font
        self._country_text = ft.Text(
            "N/A",
            size=18,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
            text_align=ft.TextAlign.CENTER,
        )

        # 2. Status Text - clean, no animation
        self._msg_text = ft.Text(
            t("app.disconnected"),
            size=13,
            weight=ft.FontWeight.W_400,
            color=ft.Colors.GREY_500,
            text_align=ft.TextAlign.CENTER,
        )

        # --- Main Layout (Centered Column) ---
        self._text_column = ft.Column(
            [self._country_text, self._msg_text],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        )

        self.content = ft.Container(
            content=self._text_column,
            padding=ft.padding.symmetric(horizontal=10),
            alignment=ft.alignment.center,
            width=320,
        )

    def update_country(self, country_data: dict = None):
        """
        Updates the country/city information.
        Persistent: Does NOT reset on disconnect.
        """
        from src.core.city_translator import translate_city
        from src.core.country_translator import translate_country

        c_name = "N/A"

        if country_data:
            # Get country code and name
            country_code = country_data.get("country_code")
            original_name = (
                country_data.get("country_name")
                or country_data.get("name")
                or "Unknown"
            )

            # Translate country name
            c_name = translate_country(country_code, original_name)

            # Translate city name if available
            city = country_data.get("city")
            if city:
                translated_city = translate_city(city)
                c_name = f"{c_name}, {translated_city}"

        self._country_text.value = c_name
        self.update()

    def set_step(self, msg: str):
        """Updates just the status message text."""
        self._msg_text.value = msg
        self._msg_text.color = ft.Colors.BLUE_400
        self.update()

    def set_status(self, msg: str):
        """Updates status message (used for mode changes etc)."""
        self._msg_text.value = msg
        self._msg_text.color = ft.Colors.GREY_500
        self.update()

    def set_initializing(self):
        self._msg_text.value = t("app.initializing")
        self._msg_text.color = ft.Colors.BLUE_400
        self.update()

    def set_connecting(self):
        self._msg_text.value = t("app.connecting")
        self._msg_text.color = ft.Colors.BLUE_400
        self.update()

    def set_connected(self, is_vpn: bool = True, country_data: dict = None):
        """Sets status to Connected."""
        self._msg_text.value = t("app.verifying")
        self._msg_text.color = ft.Colors.GREEN_400

        if country_data:
            self.update_country(country_data)
        else:
            self.update()

        threading.Thread(target=self._animate_verifying, daemon=True).start()

    def _animate_verifying(self):
        import time

        time.sleep(1.5)
        self._msg_text.value = t("app.connected")
        self._msg_text.color = ft.Colors.GREEN_400
        self.update()

    def set_disconnected(self, mode_name: str = ""):
        self._msg_text.value = t("app.disconnected")
        self._msg_text.color = ft.Colors.GREY_500
        self.update()

    def set_pre_connection_ping(self, latency_text: str, is_success: bool):
        """Updates the status text with latency (e.g. 'Ping: 45ms')."""
        import re

        if latency_text == "...":
            self._msg_text.value = t("app.checking")
            self._msg_text.color = ft.Colors.GREY_500
        else:
            # If success and contains number, add ping prefix
            has_number = bool(re.search(r"\d+", latency_text))
            prefix = (
                f"{t('connection.ping_prefix')} " if is_success and has_number else ""
            )
            self._msg_text.value = f"{prefix}{latency_text}"

            if is_success:
                # Simple Green logic
                self._msg_text.color = ft.Colors.GREEN_400
            else:
                self._msg_text.color = ft.Colors.RED_400

        self.update()
