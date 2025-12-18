"""Subscription list item component."""
from __future__ import annotations

from typing import Callable

import flet as ft


class SubscriptionListItem(ft.Container):
    """A subscription folder item in the server list."""

    def __init__(self, sub: dict, on_click: Callable[[dict], None]):
        self._sub = sub
        profiles = sub.get("profiles", [])
        url_display = (
            sub.get("url", "")[:30] + "..."
            if len(sub.get("url", "")) > 30
            else sub.get("url", "")
        )

        super().__init__(
            content=ft.ListTile(
                leading=ft.Icon(ft.Icons.FOLDER, color=ft.Colors.PRIMARY, size=24),
                title=ft.Text(sub["name"], weight=ft.FontWeight.BOLD, size=14),
                subtitle=ft.Text(
                    f"{len(profiles)} servers • {url_display}",
                    size=11,
                    color=ft.Colors.GREY_500,
                ),
                trailing=ft.Icon(
                    ft.Icons.ARROW_FORWARD_IOS, size=14, color=ft.Colors.GREY_400
                ),
                on_click=lambda e: on_click(sub),
                dense=True,
                content_padding=ft.padding.symmetric(horizontal=5, vertical=0),
            ),
            padding=0,
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.PRIMARY),  # More transparent
            blur=ft.Blur(15, 15, ft.BlurTileMode.MIRROR),  # Glass blur
            border=ft.border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.PRIMARY)),  # Subtle border
            margin=ft.margin.only(bottom=2),
        )
