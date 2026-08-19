"""SNI Spoof field input rows — Apple-style clean settings row components."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import t


class SniFieldRow(ft.Container):
    """A clean, borderless Apple macOS/iOS style setting row:

    Label on the left (light muted text) + borderless transparent field on the right.
    """

    def __init__(
        self,
        *,
        initial_value: str,
        on_change: Callable,
        label_key: str,
        label_default: str,
        hint_default: str,
        icon: Optional[ft.Icons] = None,
        numeric: bool = False,
    ):
        self._label = ft.Text(
            t(label_key, default=label_default),
            size=13,
            weight=ft.FontWeight.W_300,
            color=ft.Colors.with_opacity(0.75, ft.Colors.WHITE),
        )

        self._field = ft.TextField(
            value=initial_value,
            hint_text=hint_default,
            hint_style=ft.TextStyle(
                color=ft.Colors.with_opacity(0.30, ft.Colors.WHITE),
                size=13,
                weight=ft.FontWeight.W_300,
            ),
            text_size=13,
            text_align=ft.TextAlign.RIGHT,
            cursor_color="#A78BFA",
            cursor_width=1.5,
            keyboard_type=ft.KeyboardType.NUMBER if numeric else ft.KeyboardType.TEXT,
            border=ft.InputBorder.NONE,
            bgcolor=ft.Colors.TRANSPARENT,
            content_padding=ft.Padding.symmetric(horizontal=6, vertical=5),
            on_change=on_change,
            expand=True,
        )

        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        content=self._label,
                        width=170,
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                    ft.Container(
                        content=self._field,
                        expand=True,
                        alignment=ft.Alignment.CENTER_RIGHT,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=4, vertical=1),
            expand=True,
        )

    @property
    def value(self) -> str:
        return self._field.value or ""

    @property
    def field(self) -> ft.TextField:
        return self._field

    def set_value(self, value: str) -> None:
        self._field.value = value
        try:
            if self._field.page:
                self._field.update()
        except Exception:
            pass


class SniStatusChip(ft.Container):
    """Running / Stopped minimal flat status badge."""

    def __init__(self):
        self._dot = ft.Container(
            width=6,
            height=6,
            border_radius=3,
            bgcolor=ft.Colors.with_opacity(0.60, "#f87171"),
        )
        self._label = ft.Text(
            t("sni_spoof.stopped", default="Stopped"),
            size=11,
            weight=ft.FontWeight.W_400,
            color="#f87171",
        )
        super().__init__(
            content=ft.Row(
                [self._dot, self._label],
                spacing=5,
                tight=True,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.08, "#f87171"),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.15, "#f87171")),
        )

    def set_status(self, running: bool) -> None:
        color = "#4ADE80" if running else "#f87171"
        self.bgcolor = ft.Colors.with_opacity(0.08, color)
        self.border = ft.Border.all(1, ft.Colors.with_opacity(0.15, color))
        self._dot.bgcolor = color
        self._label.value = t(
            "sni_spoof.running" if running else "sni_spoof.stopped",
            default="Running" if running else "Stopped",
        )
        self._label.color = color
        try:
            if self.page:
                self.update()
        except Exception:
            pass
