"""Terminal Window Component for Logs Page."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors, create_glass_container


class TerminalWindow(ft.Container):
    """Terminal window glass container holding log output, status indicators, and action buttons."""

    def __init__(
        self,
        log_text_control: ft.Control,
        on_copy_click: Callable,
        on_download_click: Callable,
        on_clear_click: Callable,
    ):
        WHITE = ft.Colors.WHITE
        button_shape = ft.RoundedRectangleBorder(radius=8)

        copy_btn = ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CONTENT_COPY, size=14, color=WHITE),
                    ft.Text(t("logs.copy", default="Copy"), size=11, color=WHITE),
                ],
                spacing=4,
            ),
            style=ft.ButtonStyle(
                shape=button_shape,
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            ),
            on_click=on_copy_click,
        )

        download_btn = ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.DOWNLOAD, size=14, color=WHITE),
                    ft.Text(t("logs.download", default="Download"), size=11, color=WHITE),
                ],
                spacing=4,
            ),
            style=ft.ButtonStyle(
                shape=button_shape,
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            ),
            on_click=on_download_click,
        )

        clear_btn = ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.DELETE_OUTLINED, size=14, color="#f43f5e"),
                    ft.Text(t("logs.clear", default="Clear"), size=11, color="#f43f5e"),
                ],
                spacing=4,
            ),
            style=ft.ButtonStyle(
                shape=button_shape,
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                side=ft.BorderSide(1.0, ft.Colors.with_opacity(0.3, "#f43f5e")),
                bgcolor=ft.Colors.with_opacity(0.08, "#f43f5e"),
            ),
            on_click=on_clear_click,
        )

        glass = create_glass_container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        width=10,
                                        height=10,
                                        shape=ft.BoxShape.CIRCLE,
                                        bgcolor=AppColors.ERROR,
                                    ),
                                    ft.Container(
                                        width=10,
                                        height=10,
                                        shape=ft.BoxShape.CIRCLE,
                                        bgcolor=AppColors.PRIMARY,
                                    ),
                                    ft.Container(
                                        width=10,
                                        height=10,
                                        shape=ft.BoxShape.CIRCLE,
                                        bgcolor=AppColors.SECONDARY,
                                    ),
                                    ft.Text(
                                        t(
                                            "logs.terminal_title",
                                            default="XenRay CLI :: Main Logger",
                                        ),
                                        size=11,
                                        weight=ft.FontWeight.W_600,
                                        color=AppColors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                spacing=8,
                            ),
                            ft.Row(
                                [copy_btn, download_btn, clear_btn],
                                spacing=6,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)),
                    ft.Container(content=log_text_control, expand=True),
                ],
                spacing=8,
                expand=True,
            ),
            expand=True,
            padding=16,
        )

        super().__init__(
            content=glass.content,
            expand=glass.expand,
            padding=glass.padding,
            bgcolor=glass.bgcolor,
            border=glass.border,
            border_radius=glass.border_radius,
            blur=glass.blur,
        )
