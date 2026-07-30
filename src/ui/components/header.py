"""Header component with i18n support."""
import flet as ft

from src.core.i18n import t
from src.ui.theme import AppColors


class Header(ft.Container):
    def __init__(self, page: ft.Page, on_logs_click, on_settings_click):
        self._page = page

        content = ft.Row(
            [
                ft.Row([]),  # Empty left side (no branding)
                ft.Row(
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
                    ]
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        super().__init__(
            content=content,
            padding=ft.Padding.symmetric(horizontal=20, vertical=20),
        )

    def update_theme(self, is_dark: bool):
        """Update icon colors based on theme."""
        icon_color = ft.Colors.WHITE if is_dark else ft.Colors.BLACK87
        for child in self.content.controls[1].controls:
            if isinstance(child, ft.IconButton):
                child.icon_color = icon_color
        try:
            self.update()
        except Exception:
            pass
