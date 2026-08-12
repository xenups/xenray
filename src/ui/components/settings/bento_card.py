"""Bento glass card container component for grouping settings sections."""

from __future__ import annotations

from typing import List

import flet as ft

from src.ui.theme import create_glass_container


class BentoCard(ft.Container):
    """Glass card container for grouping setting section rows."""

    def __init__(self, controls: List[ft.Control], spacing: int = 10):
        glass = create_glass_container(
            content=ft.Column(controls, spacing=spacing),
        )

        super().__init__(
            content=glass.content,
            bgcolor=glass.bgcolor,
            border=glass.border,
            border_radius=glass.border_radius,
            blur=glass.blur,
            padding=glass.padding,
        )
