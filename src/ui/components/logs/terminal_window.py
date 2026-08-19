"""Terminal Window Component for Logs Page — minimal glass console with icon action bar."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class TerminalWindow(ft.Container):
    """Terminal window glass container holding log output, minimal header, and icon action bar."""

    def __init__(
        self,
        log_text_control: ft.Control,
        on_copy_click: Callable,
        on_clear_click: Callable,
        on_toggle_tailing: Callable | None = None,
        on_download_click: Callable | None = None,  # accepted for backward-compat
    ):
        btn_style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
            padding=ft.Padding.all(6),
        )

        self._on_copy_click = on_copy_click
        self._on_clear_click = on_clear_click
        self._external_toggle_tailing = on_toggle_tailing
        self._tailing_enabled = False

        self._copy_btn = ft.IconButton(
            icon=ft.Icons.CONTENT_COPY_ROUNDED,
            icon_size=17,
            icon_color="#94A3B8",
            tooltip=t("logs.copy_tooltip", default="Copy Logs"),
            style=btn_style,
            on_click=on_copy_click,
        )

        self._clear_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
            icon_size=17,
            icon_color="#94A3B8",
            tooltip=t("logs.clear_tooltip", default="Clear Console"),
            style=btn_style,
            on_click=on_clear_click,
        )

        self._toggle_tail_btn = ft.IconButton(
            icon=ft.Icons.PLAY_ARROW_ROUNDED,
            icon_size=18,
            icon_color="#94A3B8",
            tooltip=t("logs.stream_tooltip", default="Pause / Resume Stream"),
            style=btn_style,
            on_click=self._on_toggle_handler,
        )

        title_text = ft.Text(
            t("logs.live_logs", default="Live Logs"),
            size=13,
            weight=ft.FontWeight.W_400,
            color="#94A3B8",
        )

        toolbar_row = ft.Row(
            [self._toggle_tail_btn, self._copy_btn, self._clear_btn],
            spacing=6,
            alignment=ft.MainAxisAlignment.END,
        )

        header_row = ft.Row(
            [title_text, toolbar_row],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        super().__init__(
            content=ft.Column(
                [
                    header_row,
                    ft.Divider(height=1, color=ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
                    ft.Container(content=log_text_control, expand=True),
                ],
                spacing=8,
                expand=True,
            ),
            expand=True,
            padding=14,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
            border_radius=14,
        )

    def _on_toggle_handler(self, e) -> None:
        if self._external_toggle_tailing:
            self._external_toggle_tailing(e)
        self._tailing_enabled = not self._tailing_enabled
        self._swap_tail_button()

    def _swap_tail_button(self) -> None:
        """Toggle icon between Play and Pause states."""
        if self._tailing_enabled:
            self._toggle_tail_btn.icon = ft.Icons.PAUSE_ROUNDED
            self._toggle_tail_btn.icon_color = "#A78BFA"
            self._toggle_tail_btn.tooltip = t("logs.pause_tooltip", default="Pause Stream")
        else:
            self._toggle_tail_btn.icon = ft.Icons.PLAY_ARROW_ROUNDED
            self._toggle_tail_btn.icon_color = "#94A3B8"
            self._toggle_tail_btn.tooltip = t("logs.resume_tooltip", default="Resume Stream")
        try:
            if self._toggle_tail_btn.page:
                self._toggle_tail_btn.update()
        except Exception:
            pass
