"""Timer display component for showing connection time at top of page."""

import threading
import time

import flet as ft
from src.ui.helpers.ui_thread_helper import UIThreadHelper

from src.core.i18n import get_language, t


def to_persian_numerals(text: str) -> str:
    """Convert Latin numerals to Persian numerals."""
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    latin_digits = "0123456789"
    result = text
    for latin, persian in zip(latin_digits, persian_digits):
        result = result.replace(latin, persian)
    return result


class TimerDisplay(ft.Container):
    """
    Displays the connection timer at the top of the page.
    Shows "Tap to Connect" when disconnected, timer when connected.
    """

    def __init__(self):
        super().__init__()

        self._is_connected = False
        self._timer_running = False
        self._start_time = 0
        self._timer_thread = None

        # Main timer text with fixed width for monospace-like display
        self._timer_text = ft.Text(
            t("app.tap_to_connect"),
            size=18,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
        )

        # Use a fixed-width container for timer to prevent shifting
        self.content = ft.Container(
            content=self._timer_text,
            alignment=ft.Alignment.CENTER,
            padding=ft.padding.only(top=10),
            width=200,  # Fixed width to prevent shifting
        )

    def _format_timer(self, hours: int, minutes: int, seconds: int) -> str:
        """Format timer with appropriate numerals based on language."""
        timer_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if get_language() == "fa":
            return to_persian_numerals(timer_str)
        return timer_str

    def set_connecting(self):
        """Show connecting state - show 00:00:00 immediately."""
        self._timer_text.value = self._format_timer(0, 0, 0)
        self._timer_text.color = "#d97706"  # Amber that works in both modes
        self._timer_text.size = 28
        self._timer_text.weight = ft.FontWeight.BOLD
        if UIThreadHelper.is_mounted(self):
            self.update()

    def set_connected(self):
        """Start the connection timer."""
        self._is_connected = True
        self._timer_text.color = "#7c3aed"  # Purple that works in both light and dark
        self._timer_text.size = 28
        self._timer_text.weight = ft.FontWeight.BOLD
        self._start_timer()
        self.update()

    def _start_timer(self):
        """Start the connection timer."""
        self._timer_running = True
        self._start_time = time.time()

        def timer_loop():
            while self._timer_running and self._is_connected:
                elapsed = int(time.time() - self._start_time)
                hours = elapsed // 3600
                minutes = (elapsed % 3600) // 60
                seconds = elapsed % 60
                self._timer_text.value = self._format_timer(hours, minutes, seconds)
                try:
                    self.update()
                except Exception:
                    break
                time.sleep(1)

        self._timer_thread = threading.Thread(target=timer_loop, daemon=True)
        self._timer_thread.start()

    def _stop_timer(self):
        """Stop the connection timer."""
        self._timer_running = False

    def set_disconnected(self):
        """Reset to disconnected state."""
        self._is_connected = False
        self._stop_timer()
        self._timer_text.value = t("app.tap_to_connect")
        self._timer_text.color = ft.Colors.ON_SURFACE_VARIANT
        self._timer_text.size = 18
        self._timer_text.weight = ft.FontWeight.W_500
        self.update()
