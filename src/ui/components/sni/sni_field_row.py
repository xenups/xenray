"""SNI Spoof field input rows — reusable components.

Mirror the settings component architecture (e.g. settings/port_input_row.py):
each field is a self-contained ``ft.Container`` with an icon, label, hint and a
bound TextField. The view composes them, it does not inline every TextField.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t

ICON_ACCENT = "#8B5CF6"


def _input_styles():
    return {
        "border_color": ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
        "focused_border_color": "#7c3aed",
        "bgcolor": "#0a0d14",
        "text_size": 13,
        "cursor_color": "#A78BFA",
        "content_padding": ft.Padding.symmetric(horizontal=12, vertical=11),
    }


class SniFieldRow(ft.Container):
    """A labelled, icon-prefixed text input row for an SNI spoof setting.

    Mirrors the settings-architecture row style: icon + label + field, top-level
    bounded so save/change handlers stay with the component's controller hook.
    """

    def __init__(
        self,
        *,
        initial_value: str,
        on_change: Callable,
        label_key: str,
        label_default: str,
        hint_default: str,
        icon: ft.Icons,
        numeric: bool = False,
    ):
        self._field = ft.TextField(
            value=initial_value,
            label=t(label_key, default=label_default),
            hint_text=hint_default,
            prefix=ft.Container(
                content=ft.Icon(icon, color=ICON_ACCENT, size=16),
                margin=ft.Margin.only(right=8, left=2),
            ),
            keyboard_type=ft.KeyboardType.NUMBER if numeric else ft.KeyboardType.TEXT,
            border_radius=10,
            expand=1,
            on_change=on_change,
            **_input_styles(),
        )
        super().__init__(content=self._field, expand=True)

    @property
    def value(self) -> str:
        return self._field.value or ""

    def set_value(self, value: str) -> None:
        self._field.value = value
        try:
            if self._field.page:
                self._field.update()
        except RuntimeError:
            pass


class SniStatusChip(ft.Container):
    """Running / Stopped status indicator chip (mirrors dashboard status chips)."""

    def __init__(self):
        self._dot = ft.Container(
            width=7,
            height=7,
            border_radius=4,
            bgcolor=ft.Colors.with_opacity(0.5, "#f87171"),
        )
        self._label = ft.Text(
            t("sni_spoof.stopped", default="Stopped"),
            size=11,
            weight=ft.FontWeight.W_600,
            color="#f87171",
        )
        super().__init__(
            content=ft.Row(
                [self._dot, self._label],
                spacing=5,
                tight=True,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.10, "#f87171"),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.18, "#f87171")),
        )

    def set_status(self, running: bool) -> None:
        color = "#4ADE80" if running else "#f87171"
        self.bgcolor = ft.Colors.with_opacity(0.10, color)
        self.border = ft.Border.all(1, ft.Colors.with_opacity(0.20, color))
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
