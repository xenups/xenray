"""Header component with i18n support."""
import flet as ft

from src.core.i18n import t


class Header(ft.Container):
    def __init__(self, page: ft.Page, on_logs_click, on_settings_click, lan_sharing_card: ft.Control | None = None):
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
            # Fully transparent - no background, part of main window
        )
