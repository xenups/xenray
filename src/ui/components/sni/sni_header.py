"""SNI Header component — page title, subtitle, status chip and master switch."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.components.sni.sni_field_row import SniStatusChip


class SniHeader(ft.Container):
    """Header row: shield icon + title + subtitle (left), status chip + master
    switch (right). Self-contained; the page passes callbacks in.
    """

    def __init__(
        self,
        *,
        is_rtl: bool,
        enabled: bool,
        on_toggle_change: Callable,
    ):
        self._status_chip = SniStatusChip()
        self._master_switch = ft.Switch(
            value=enabled,
            active_color="#4ADE80",
            on_change=on_toggle_change,
        )

        left_header = ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ft.Icons.SHIELD_ROUNDED, size=20, color="#A78BFA"),
                            padding=6,
                            border_radius=8,
                            bgcolor=ft.Colors.with_opacity(0.14, "#6d28d9"),
                            border=ft.Border.all(1, ft.Colors.with_opacity(0.25, "#6d28d9")),
                        ),
                        ft.Text(
                            t("sni_spoof.title", default="SNI Spoofing"),
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE,
                            rtl=is_rtl,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(
                    content=ft.Text(
                        t(
                            "sni_spoof.subtitle",
                            default="Hide the real SNI from DPI by sending a fake TLS Server Name",
                        ),
                        size=12,
                        color="#8E8C99",
                        rtl=is_rtl,
                    ),
                    padding=ft.Padding.only(left=2),
                ),
            ],
            spacing=4,
            expand=True,
        )

        right_header = ft.Row(
            [self._status_chip, self._master_switch],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        super().__init__(
            content=ft.Row(
                [left_header, right_header],
                vertical_alignment=ft.CrossAxisAlignment.START,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            margin=ft.Margin.only(bottom=18),
        )

    @property
    def status_chip(self) -> SniStatusChip:
        return self._status_chip

    @property
    def master_switch(self) -> ft.Switch:
        return self._master_switch

    def set_status(self, running: bool) -> None:
        self._status_chip.set_status(running)
