"""Auto-reconnect settings section."""

from __future__ import annotations

import flet as ft

from src.ui.components.settings.auto_reconnect_toggle_row import AutoReconnectToggleRow


class AutoReconnectSection(ft.Container):
    """Application subsection holding the auto-reconnect toggle row."""

    def __init__(self, auto_reconnect_row: AutoReconnectToggleRow):
        self._auto_reconnect_row = auto_reconnect_row
        super().__init__(
            content=ft.Column(
                [auto_reconnect_row],
                spacing=8,
            )
        )

    @property
    def auto_reconnect_row(self) -> AutoReconnectToggleRow:
        return self._auto_reconnect_row
