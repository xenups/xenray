"""Header component with i18n support."""

from __future__ import annotations

import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors


class Header(ft.Container):
    def __init__(
        self,
        page: ft.Page,
        on_logs_click,
        on_settings_click,
        lan_sharing_card: ft.Control | None = None,
    ):
        self._page = page

        left_side = ft.Row(
            [lan_sharing_card] if lan_sharing_card else [],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        right_side = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARTICLE_OUTLINED,
                    tooltip=t("header.logs"),
                    on_click=on_logs_click,
                ),
                ft.IconButton(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    tooltip=t("header.settings"),
                    on_click=on_settings_click,
                ),
            ],
            alignment=ft.MainAxisAlignment.END,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
        )

        content = ft.Row(
            [
                left_side,
                right_side,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        super().__init__(
            content=content,
            padding=ft.Padding.symmetric(horizontal=16, vertical=16),
        )

    def update_theme(self, is_dark: bool):
        """Update icon colors based on theme."""
        icon_color = ft.Colors.WHITE if is_dark else ft.Colors.BLACK87
        if (
            isinstance(self.content, ft.Row)
            and len(self.content.controls) > 1
            and isinstance(self.content.controls[1], ft.Row)
        ):
            for child in self.content.controls[1].controls:
                if isinstance(child, ft.IconButton):
                    child.icon_color = icon_color
        try:
            self.update()
        except Exception:
            pass
