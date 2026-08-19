"""SNI Header component — compact page title and master switch."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.components.sni.sni_field_row import SniStatusChip


class SniHeader(ft.Container):
    """Compact header row: Title (left) + Master Switch (right)."""

    def __init__(
        self,
        *,
        is_rtl: bool,
        enabled: bool,
        on_toggle_change: Callable,
    ):
        self._status_chip = SniStatusChip()
        self._status_chip.visible = False

        self._master_switch = ft.Switch(
            value=enabled,
            active_color="#8B5CF6",
            on_change=on_toggle_change,
        )

        title_text = ft.Text(
            t("sni_spoof.title", default="SNI Spoofing"),
            size=18,
            weight=ft.FontWeight.W_300,
            style=ft.TextStyle(letter_spacing=0.8),
            color=ft.Colors.WHITE,
            rtl=is_rtl,
        )

        super().__init__(
            content=ft.Row(
                [title_text, self._master_switch],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            margin=ft.Margin.only(bottom=10),
            padding=ft.Padding.symmetric(horizontal=2, vertical=2),
        )

    @property
    def status_chip(self) -> SniStatusChip:
        return self._status_chip

    @property
    def master_switch(self) -> ft.Switch:
        return self._master_switch

    def set_status(self, running: bool) -> None:
        self._status_chip.set_status(running)
