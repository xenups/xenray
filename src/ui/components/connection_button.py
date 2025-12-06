import flet as ft


class ConnectionButton(ft.UserControl):
    """Connection button with pulsing glow animation during connecting."""
    
    def __init__(self, on_click):
        super().__init__()
        self.on_click = on_click
        self._icon = ft.Icon(ft.icons.POWER_SETTINGS_NEW, size=60, color=ft.colors.WHITE)
        self._container = None
        self._is_connected = False

    def build(self):
        self._container = ft.Container(
            content=self._icon,
            width=180,
            height=180,
            border_radius=90,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=["#2b2d42", "#1a1b26"], 
            ),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=15,
                color=ft.colors.SHADOW,
                offset=ft.Offset(0, 5),
            ),
            on_click=self.on_click,
            animate=ft.animation.Animation(500, ft.AnimationCurve.EASE_IN_OUT),
            alignment=ft.alignment.center,
            border=ft.border.all(2, ft.colors.OUTLINE)
        )
        
        return self._container

    def update_theme(self, is_dark: bool):
        """Update button appearance based on theme."""
        if self._is_connected:
            return

        if is_dark:
            self._icon.color = ft.colors.WHITE
            self._container.gradient.colors = ["#2b2d42", "#1a1b26"]
            self._container.border = ft.border.all(2, "#3b3e5b")
        else:
            self._icon.color = ft.colors.GREY_700
            self._container.gradient.colors = ["#ffffff", "#f0f0f0"]
            self._container.border = ft.border.all(2, "#e0e0e0")
        self.update()

    def set_connected(self):
        self._is_connected = True
        self._container.gradient = ft.LinearGradient(
            colors=["#6d28d9", "#4c1d95"],
        )
        self._container.border = ft.border.all(2, "#8b5cf6")
        self._container.shadow.color = "#8b5cf6"
        self._container.shadow.blur_radius = 30
        self._container.shadow.spread_radius = 1
        self._icon.color = ft.colors.WHITE
        self.update()

    def set_disconnected(self):
        self._is_connected = False
        is_dark = self.page.theme_mode == ft.ThemeMode.DARK if self.page else True
        self.update_theme(is_dark)
        self._container.shadow.blur_radius = 15
        self._container.shadow.spread_radius = 1
        self._container.shadow.color = ft.colors.SHADOW
        self.update()

    def set_connecting(self):
        """Set connecting state with pulsing amber glow."""
        self._container.border = ft.border.all(3, "#fbbf24")
        self._container.shadow.color = "#fbbf24"
        self._container.shadow.blur_radius = 40
        self._container.shadow.spread_radius = 8
        self.update()
