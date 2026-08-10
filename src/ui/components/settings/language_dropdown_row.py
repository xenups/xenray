"""Language dropdown component with flag icons for settings."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class LanguageDropdownRow(ft.Container):
    """Language dropdown row with flag images."""

    def __init__(self, current_value: str, on_change: Callable):
        self._languages = [
            ("en", "gb", "English"),
            ("fa", "ir", "فارسی"),
            ("zh", "cn", "中文"),
            ("ru", "ru", "Русский"),
        ]

        self._dropdown = ft.Dropdown(
            width=160,
            text_size=12,
            content_padding=8,
            value=current_value if current_value else "en",
            options=[ft.dropdown.Option(lang_code, f"{name}") for lang_code, flag_code, name in self._languages],
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
        )

        current_flag = "gb"
        for lang_code, flag_code, name in self._languages:
            if lang_code == (current_value or "en"):
                current_flag = flag_code
                break

        self._flag_image = ft.Image(
            src=f"/flags/{current_flag}.svg",
            width=24,
            height=18,
            fit=ft.BoxFit.COVER,
            border_radius=3,
            filter_quality=ft.FilterQuality.HIGH,
            anti_alias=True,
        )

        original_on_change = on_change

        def wrapped_on_change(e):
            selected = getattr(e, "control", None)
            value = selected.value if selected is not None else None
            if not value:
                value = self._dropdown.value
            for lang_code, flag_code, _ in self._languages:
                if lang_code == value:
                    self._flag_image.src = f"/flags/{flag_code}.svg"
                    try:
                        self._flag_image.update()
                    except Exception:
                        pass
                    break
            original_on_change(e)

        self._dropdown.on_select = wrapped_on_change

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.LANGUAGE, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        t("settings.language"),
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    self._flag_image,
                                ],
                                spacing=6,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(
                                t(
                                    "settings.language_description",
                                    default="Interface display language",
                                ),
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    self._dropdown,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        )

    @property
    def value(self) -> str:
        return self._dropdown.value
