"""Status display component for showing connection status."""

import threading

import flet as ft

from src.core.i18n import t


class StatusDisplay(ft.Container):
    """
    Displays the current connection status and country information.
    Layout: Stack( Center(TextColumn), Left(Flag) )
    """

    def __init__(self):
        super().__init__()

        # --- Controls ---

        # 1. Country/City Name
        self._country_text = ft.Text(
            "N/A",
            size=16,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.ON_SURFACE,
            text_align=ft.TextAlign.CENTER,
        )

        # 2. Status Text
        self._msg_text = ft.Text(
            t("app.disconnected"),
            size=12,
            color=ft.Colors.GREY_500,
            text_align=ft.TextAlign.CENTER,
        )
        self._dots_text = ft.Text(
            ".", size=12, color=ft.Colors.GREY_500, visible=False, width=20
        )

        # Status Row (Msg + Dots)
        self._status_row = ft.Row(
            [self._msg_text, self._dots_text],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=0,
            tight=True,
        )

        # --- Main Layout (Centered Column) ---
        self._text_column = ft.Column(
            [self._country_text, self._status_row],
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

        self._dots_timer = None
        self._dots_count = 0

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
        self._stop_dots_animation()
        self._dots_text.visible = False
        self._msg_text.value = msg
        self._msg_text.color = ft.Colors.GREY_500
        self.update()

    def set_initializing(self):
        self._stop_dots_animation()
        self._msg_text.value = t("app.initializing")
        self._msg_text.color = ft.Colors.BLUE_400
        self._dots_text.visible = True
        self._start_dots_animation()
        self.update()

    def set_connecting(self):
        self._stop_dots_animation()
        self._msg_text.value = t("app.connecting")
        self._msg_text.color = ft.Colors.BLUE_400
        self._dots_text.visible = True
        self._start_dots_animation()
        self.update()

    def set_connected(self, is_vpn: bool = True, country_data: dict = None):
        """Sets status to Connected."""
        self._stop_dots_animation()
        self._msg_text.value = t("app.verifying")
        self._msg_text.color = ft.Colors.GREEN_400
        self._dots_text.visible = True
        self._start_dots_animation()

        if country_data:
            self.update_country(country_data)
        else:
            self.update()

        threading.Thread(target=self._animate_verifying, daemon=True).start()

    def _animate_verifying(self):
        import time

        time.sleep(1.5)
        self._stop_dots_animation()
        self._dots_text.visible = False
        self._msg_text.value = t("app.connected")
        self._msg_text.color = ft.Colors.GREEN_400
        self.update()

    def set_disconnected(self, mode_name: str = ""):
        self._stop_dots_animation()
        self._dots_text.visible = False
        self._msg_text.value = t("app.disconnected")
        self._msg_text.color = ft.Colors.GREY_500
        self.update()

    def set_pre_connection_ping(self, latency_text: str, is_success: bool):
        """Updates the status text with latency (e.g. 'Ping: 45ms')."""
        import re

        self._stop_dots_animation()
        self._dots_text.visible = False

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

    # --- Animation Helpers ---
    def _start_dots_animation(self):
        self._dots_count = 0

        def _anim():
            while self._dots_text.visible:
                self._dots_count = (self._dots_count + 1) % 4
                self._dots_text.value = "." * self._dots_count
                try:
                    self._dots_text.update()
                except:
                    break
                import time

                time.sleep(0.5)

        self._dots_timer = threading.Thread(target=_anim, daemon=True)
        self._dots_timer.start()

    def _stop_dots_animation(self):
        self._dots_text.visible = False
        try:
            self._dots_text.update()
        except:
            pass
