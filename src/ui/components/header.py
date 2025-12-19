"""Header component with i18n support."""
import flet as ft

from src.core.i18n import t


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
            padding=ft.padding.symmetric(horizontal=20, vertical=20),
            # Fully transparent - no background, part of main window
        )
