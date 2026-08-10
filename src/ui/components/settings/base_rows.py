"""Base layout components for settings sections, headers, and rows."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.ui.theme import AppColors


class SectionHeader(ft.Container):
    """Reusable settings section header with icon and bold title."""

    def __init__(self, icon: str, title: str):
        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(icon, color=AppColors.PRIMARY, size=22),
                        width=28,
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                    ft.Text(
                        title,
                        size=16,
                        weight=ft.FontWeight.W_700,
                        color=ft.Colors.WHITE,
                    ),
                ],
                spacing=12,
            ),
            padding=ft.Padding.only(left=8, right=8, top=4, bottom=10),
            border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.12, ft.Colors.WHITE))),
        )


class SettingsSection(ft.Container):
    """Base class for a settings section with a title."""

    def __init__(self, title: str, controls: list, padding_horizontal: int = 20):
        super().__init__(
            content=ft.Column(
                [
                    ft.Text(
                        title,
                        color=ft.Colors.WHITE,
                        weight=ft.FontWeight.BOLD,
                        size=12,
                    ),
                    ft.Container(height=5),
                    *controls,
                ]
            ),
            padding=ft.Padding.symmetric(horizontal=padding_horizontal),
        )


class SettingsRow(ft.Container):
    """A row in a settings section with icon, label, and control."""

    def __init__(
        self,
        icon: str,
        label: str,
        control: ft.Control,
        sublabel: Optional[str] = None,
        sublabel_control: Optional[ft.Control] = None,
    ):
        label_column = ft.Column(
            [
                ft.Text(label, weight=ft.FontWeight.W_500),
            ],
            spacing=2,
            expand=True,
        )

        if sublabel_control:
            label_column.controls.append(sublabel_control)
        elif sublabel:
            label_column.controls.append(ft.Text(sublabel, size=11, color=ft.Colors.ON_SURFACE_VARIANT))

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(icon, color=ft.Colors.ON_SURFACE_VARIANT),
                    label_column,
                    control,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=10,
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        )


class SettingsListTile(ft.Container):
    """A styled, interactive container list tile for settings navigation with badge support."""

    def __init__(
        self,
        icon: str,
        title: str,
        subtitle: str,
        on_click: Optional[Callable] = None,
        show_chevron: bool = True,
        badge_text: Optional[str] = None,
    ):
        self._on_click = on_click
        self._chevron_icon = ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=ft.Colors.PRIMARY)

        badge_control = None
        if badge_text:
            badge_control = ft.Container(
                content=ft.Text(
                    badge_text,
                    size=11,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.PRIMARY,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                border_radius=8,
                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.PRIMARY)),
            )

        trailing_controls = []
        if badge_control:
            trailing_controls.append(badge_control)
        if show_chevron:
            trailing_controls.append(self._chevron_icon)

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(icon, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column(
                        [
                            ft.Text(title, weight=ft.FontWeight.W_500),
                            ft.Text(
                                subtitle,
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Row(
                        trailing_controls,
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
            on_click=on_click,
            on_hover=self._handle_hover,
            ink=True,
        )

    def _handle_hover(self, e):
        """Interactive hover transition."""
        if e.data == "true":
            self.bgcolor = ft.Colors.with_opacity(0.18, ft.Colors.ON_SURFACE)
            self.border = ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.PRIMARY))
        else:
            self.bgcolor = ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
            self.border = None
        try:
            if self.page:
                self.update()
        except Exception:
            pass
