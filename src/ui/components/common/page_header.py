"""Page header component with title, optional subtitle, back button, and actions."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft


class PageHeader(ft.Container):
    """Reusable page header container."""

    def __init__(
        self,
        title: str,
        subtitle: Optional[str] = None,
        on_back: Optional[Callable] = None,
        actions: Optional[list[ft.Control]] = None,
    ):
        controls: list[ft.Control] = []
        if on_back:
            controls.append(ft.IconButton(ft.Icons.ARROW_BACK, on_click=on_back))

        title_col_controls = [ft.Text(title, size=20, weight=ft.FontWeight.BOLD)]
        if subtitle:
            title_col_controls.append(ft.Text(subtitle, size=12, color=ft.Colors.ON_SURFACE_VARIANT))

        controls.append(ft.Column(title_col_controls, spacing=2, expand=True))

        if actions:
            controls.extend(actions)

        super().__init__(
            content=ft.Row(controls, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=15, vertical=10),
            bgcolor=ft.Colors.with_opacity(0.2, "#1e293b"),
            blur=ft.Blur(10, 10, ft.BlurTileMode.MIRROR),
        )
