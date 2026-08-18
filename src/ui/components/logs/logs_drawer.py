"""Logs drawer component with source selector, network stats and i18n support.

Features:
- Source selector: App logs / Xray-core / Sing-box (user picks what to tail).
- Tailer starts OFF — no CPU overhead until the user explicitly enables it.
- Polling interval control (0.5s / 1s / 2s / 5s) — respects performance.
- Pause/resume, heartbeat, network stats as before.
"""

import flet as ft

from src.core.constants import SINGBOX_LOG_FILE, XRAY_LOG_FILE
from src.core.i18n import get_language, t
from src.core.logger import log_file as APP_LOG_FILE
from src.ui.components.logs.log_viewer import LogViewer


def to_persian_numerals(text: str) -> str:
    """Convert Latin numerals to Persian numerals."""
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    latin_digits = "0123456789"
    result = text
    for latin, persian in zip(latin_digits, persian_digits):
        result = result.replace(latin, persian)
    return result


# Log source definitions: label key + file(s) to tail
LOG_SOURCES = {
    "app": ("logs.source_app", [APP_LOG_FILE]),
    "xray": ("logs.source_xray", [XRAY_LOG_FILE]),
    "singbox": ("logs.source_singbox", [SINGBOX_LOG_FILE]),
}

# Polling intervals exposed to the user (seconds)
TAIL_INTERVALS = [0.5, 1.0, 2.0, 5.0]


class LogsDrawer(ft.NavigationDrawer):
    """Logs drawer component with source selector + network stats."""

    def __init__(self, log_viewer: LogViewer, heartbeat: ft.Container):
        self._log_viewer = log_viewer
        self._heartbeat = heartbeat
        self._heartbeat.animate_opacity = 500

        # Active log source (default: app logs) — but tailing starts OFF.
        self._active_source = "app"
        self._tailing_enabled = False

        self._pause_button = ft.IconButton(
            icon=ft.Icons.PAUSE_ROUNDED,
            tooltip=t("logs.pause"),
            on_click=self._toggle_log_pause,
            icon_color=ft.Colors.RED_600,
        )

        # --- Source selector (App / Xray / Sing-box) ---
        self._source_dropdown = ft.Dropdown(
            value="app",
            label=t("logs.source", default="Log Source"),
            width=150,
            dense=True,
            options=[
                ft.dropdown.Option(key=key, text=t(label_key, default=key))
                for key, (label_key, _) in LOG_SOURCES.items()
            ],
            on_select=self._on_source_changed,
        )

        # --- Enable / disable tailing (OFF by default — zero CPU) ---
        # High-contrast filled button: green "Start" invites the click, red
        # "Stop" is unmissable while tailing. White text on both states.
        self._TAIL_BTN_OFF_BG = "#4ADE80"
        self._TAIL_BTN_ON_BG = "#f43f5e"
        self._toggle_tail_btn = ft.FilledButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, size=18, color=ft.Colors.WHITE),
                    ft.Text(
                        t("logs.enable", default="Enable"),
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
            height=32,
            on_click=self._toggle_tailing,
            style=ft.ButtonStyle(
                bgcolor=self._TAIL_BTN_OFF_BG,
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding(12, 0, 12, 0),
            ),
        )

        # --- Polling interval selector ---
        self._interval_dropdown = ft.Dropdown(
            value="1.0",
            label=t("logs.interval", default="Interval"),
            width=110,
            dense=True,
            options=[ft.dropdown.Option(key=str(iv), text=f"{iv:g}s") for iv in TAIL_INTERVALS],
            on_select=self._on_interval_changed,
        )

        # Source selector + interval in one row; the START/STOP button gets its
        # OWN full-width row below so it is always visible (the drawer is
        # narrow — cramming it beside two dropdowns pushed it off-screen).
        # The button is height=32 (same size class as siblings) with an
        # explicit dark-bg contrast — visible, but not oversized.
        self._controls_row = ft.Row(
            [self._source_dropdown, self._interval_dropdown],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        self._tail_row = ft.Row(
            [self._toggle_tail_btn],
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
        )

        # Network Stats Row
        self._download_icon = ft.Icon(ft.Icons.ARROW_DOWNWARD, size=14, color=ft.Colors.GREEN_400)
        self._download_text = ft.Text(
            "0 KB/s",
            size=12,
            color=ft.Colors.GREEN_400,
            weight=ft.FontWeight.W_500,
            width=70,
        )
        self._upload_icon = ft.Icon(ft.Icons.ARROW_UPWARD, size=14, color=ft.Colors.BLUE_400)
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
                            ft.Text(t("logs.title"), size=22, weight=ft.FontWeight.BOLD),
                            ft.Row([self._pause_button, self._heartbeat], spacing=10),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=20,
                ),
                # Source selector + interval + enable (NEW)
                ft.Container(
                    content=self._controls_row,
                    padding=ft.Padding.only(left=15, right=15, bottom=6),
                ),
                # START/STOP tailing button — its own row so it is always visible
                ft.Container(
                    content=self._tail_row,
                    padding=ft.Padding.only(left=15, right=15, bottom=10),
                ),
                # Network Stats
                ft.Container(
                    content=self._stats_row,
                    padding=ft.Padding.only(bottom=10),
                ),
                ft.Divider(),
                # Logs content
                ft.Container(
                    content=self._log_viewer.control,
                    padding=ft.Padding.only(left=15, right=15, bottom=15),
                    expand=True,
                ),
            ],
            bgcolor=ft.Colors.with_opacity(0.9, "#0f172a"),
            shadow_color=ft.Colors.with_opacity(0.2, ft.Colors.BLACK),
        )

    # ------------------------------------------------------------------
    # Source / interval / enable handlers
    # ------------------------------------------------------------------

    def _on_source_changed(self, e: ft.ControlEvent) -> None:
        """Switch the tailed log source (app/xray/singbox)."""
        new_source = e.control.value if hasattr(e.control, "value") else (e.data or "app")
        if new_source not in LOG_SOURCES:
            new_source = "app"
        self._active_source = new_source
        # Restart tailing with the new source (only if the user enabled it)
        if self._tailing_enabled:
            self._log_viewer.start_tailing(*LOG_SOURCES[new_source][1])
        self._log_viewer.clear_logs()

    def _on_interval_changed(self, e: ft.ControlEvent) -> None:
        """Update the tail polling interval."""
        try:
            interval = float(e.control.value if hasattr(e.control, "value") else (e.data or "1.0"))
        except (TypeError, ValueError):
            interval = 1.0
        self._log_viewer.tail_interval = interval

    def _toggle_tailing(self, e: ft.ControlEvent) -> None:
        """Enable/disable log tailing (OFF by default — zero CPU while off)."""
        self._tailing_enabled = not self._tailing_enabled
        self._log_viewer.user_enabled = self._tailing_enabled
        if self._tailing_enabled:
            self._log_viewer.start_tailing(*LOG_SOURCES[self._active_source][1])
            self._toggle_tail_btn.content = ft.Row(
                [
                    ft.Icon(ft.Icons.STOP_CIRCLE_OUTLINED, size=18, color=ft.Colors.WHITE),
                    ft.Text(
                        t("logs.disable", default="Disable"),
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            )
        else:
            self._log_viewer.stop_tailing()
            self._toggle_tail_btn.content = ft.Row(
                [
                    ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, size=18, color=ft.Colors.WHITE),
                    ft.Text(
                        t("logs.enable", default="Enable"),
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            )
        # Swap the filled bgcolor (green Start <-> red Stop) so the state is
        # obvious at a glance even before reading the label.
        self._toggle_tail_btn.style.bgcolor = self._TAIL_BTN_ON_BG if self._tailing_enabled else self._TAIL_BTN_OFF_BG
        try:
            if self._toggle_tail_btn.page:
                self._toggle_tail_btn.update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Pause / stats (unchanged behaviour)
    # ------------------------------------------------------------------

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

        # Targeted update: only the pause button re-renders (no full page repaint).
        try:
            if self._pause_button.page:
                self._pause_button.update()
        except Exception:
            pass

    def update_network_stats(self, download_speed: str, upload_speed: str):
        """Update network stats elements (Idempotent)."""
        # Only update if values changed to prevent unnecessary repaints
        dl_val = to_persian_numerals(download_speed) if get_language() == "fa" else download_speed
        ul_val = to_persian_numerals(upload_speed) if get_language() == "fa" else upload_speed

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
