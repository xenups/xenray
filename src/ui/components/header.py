"""Header component with i18n support."""
import flet as ft

from src.core.i18n import t


class Header(ft.Container):
    def __init__(
        self, page: ft.Page, on_theme_toggle, on_logs_click, on_settings_click
    ):
        self._page = page
        self._on_theme_toggle = on_theme_toggle

        self._theme_icon = ft.IconButton(
            icon=(
                ft.Icons.NIGHTLIGHT_ROUND
                if page.theme_mode == ft.ThemeMode.DARK
                else ft.Icons.WB_SUNNY_OUTLINED
            ),
            tooltip=t("header.toggle_theme"),
            on_click=self._handle_theme_toggle,
        )

        content = ft.Row(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SHIELD_MOON, size=28, color=ft.Colors.PRIMARY),
                        ft.Text("XenRay", size=24, weight=ft.FontWeight.BOLD),
                    ]
                ),
                ft.Row(
                    [
                        self._theme_icon,
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
            bgcolor=ft.Colors.SURFACE,
            border=ft.border.only(
                bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)
            ),
        )

    def _handle_theme_toggle(self, e):
        self._on_theme_toggle(e)

    def update_theme(self, is_dark: bool):
        self._theme_icon.icon = (
            ft.Icons.NIGHTLIGHT_ROUND if is_dark else ft.Icons.WB_SUNNY_OUTLINED
        )
        self.update()
