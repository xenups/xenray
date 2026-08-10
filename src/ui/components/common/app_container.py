import flet as ft


class AppContainer(ft.Container):
    """Main wrapper for the application layout."""

    def __init__(self, content_control: ft.Control):
        super().__init__(
            expand=True,
            content=content_control,
            bgcolor=ft.Colors.TRANSPARENT,  # Let update_theme handle it
        )

    def update_theme(self, is_dark: bool):
        self.bgcolor = "#111111" if is_dark else "#f0f2f5"  # Light grey for light mode
        self.update()
