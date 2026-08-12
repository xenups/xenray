"""Startup & language settings section."""

from __future__ import annotations

import flet as ft

from src.ui.components.settings.language_dropdown_row import LanguageDropdownRow
from src.ui.components.settings.startup_toggle_row import StartupToggleRow


class StartupLanguageSection(ft.Container):
    """Application subsection composing the OS startup toggle and language selector rows."""

    def __init__(
        self,
        startup_row: StartupToggleRow,
        language_row: LanguageDropdownRow,
    ):
        self._startup_row = startup_row
        self._language_row = language_row

        super().__init__(
            content=ft.Column(
                [startup_row, language_row],
                spacing=8,
            )
        )

    @property
    def startup_row(self) -> StartupToggleRow:
        return self._startup_row

    @property
    def language_row(self) -> LanguageDropdownRow:
        return self._language_row
