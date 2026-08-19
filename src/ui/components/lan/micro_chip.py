"""LAN IP / Port micro-chip component with copy action."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import t


class MicroChip(ft.Container):
    """Reusable micro chip container for displaying IP/Port details with tap-to-copy glass styling."""

    def __init__(
        self,
        label_key: str,
        default_label: str,
        value: str,
        val_text_ctrl: Optional[ft.Text] = None,
        on_copy: Optional[Callable[[str], None]] = None,
        is_rtl: bool = False,
    ):
        self._on_copy = on_copy
        self._val_ctrl = val_text_ctrl or ft.Text(
            value,
            size=12,
            weight=ft.FontWeight.W_400,
            color="white",
            selectable=False,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        copy_icon = ft.Icon(
            ft.Icons.COPY_ROUNDED,
            size=12,
            color="#94A3B8",
        )

        super().__init__(
            expand=1,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border_radius=10,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
            on_click=lambda e: self._on_copy(self._val_ctrl.value) if self._on_copy else None,
            ink=True,
            tooltip=t("lan.tap_to_copy", default="Tap to Copy"),
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                t(label_key, default=default_label),
                                size=10,
                                color="#94A3B8",
                                weight=ft.FontWeight.W_300,
                                rtl=is_rtl,
                            ),
                            self._val_ctrl,
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    copy_icon,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def update_value(self, value: str) -> None:
        """Reactively update the chip's displayed value text."""
        self._val_ctrl.value = value
        try:
            self._val_ctrl.update()
        except Exception:
            pass
