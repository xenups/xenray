import flet as ft


class ConnectionButton(ft.Container):
    """Connection button with pulsing glow animation during connecting."""
    
    def __init__(self, on_click):
        self._icon = ft.Icon(ft.Icons.POWER_SETTINGS_NEW, size=60, color=ft.Colors.WHITE)
        self._is_connected = False
        
        super().__init__(
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
                color=ft.Colors.SHADOW,
                offset=ft.Offset(0, 5),
            ),
            on_click=on_click,
            animate=ft.Animation(500, ft.AnimationCurve.EASE_IN_OUT),
            alignment=ft.alignment.center,
            border=ft.border.all(2, ft.Colors.OUTLINE)
        )

    def update_theme(self, is_dark: bool):
        """Update button appearance based on theme."""
        if self._is_connected:
            return

        if is_dark:
            self._icon.color = ft.Colors.WHITE
            self.gradient.colors = ["#2b2d42", "#1a1b26"]
            self.border = ft.border.all(2, "#3b3e5b")
            self.shadow.color = ft.Colors.SHADOW
            self.shadow.blur_radius = 15
        else:
            self._icon.color = ft.Colors.GREY_700
            self.gradient.colors = ["#ffffff", "#f0f0f0"]
            self.border = ft.border.all(2, "#e0e0e0")
            # Reduced shadow for light mode
            self.shadow.color = ft.Colors.with_opacity(0.1, ft.Colors.BLACK)
            self.shadow.blur_radius = 8
        self.update()

    def set_connected(self):
        self._is_connected = True
        self.gradient = ft.LinearGradient(
            colors=["#6d28d9", "#4c1d95"],
        )
        self.border = ft.border.all(2, "#8b5cf6")
        self.shadow.color = "#8b5cf6"
        self.shadow.blur_radius = 30
        self.shadow.spread_radius = 1
        self._icon.color = ft.Colors.WHITE
        self.update()

    def set_disconnected(self):
        self._is_connected = False
        is_dark = self.page.theme_mode == ft.ThemeMode.DARK if self.page else True
        self.update_theme(is_dark)
        self.shadow.blur_radius = 15
        self.shadow.spread_radius = 1
        self.shadow.color = ft.Colors.SHADOW
        self.update()

    def set_connecting(self):
        """Set connecting state with pulsing amber glow."""
        self._is_connected = False # Ensure we are not in connected state
        self._animate_pulse()

    def _animate_pulse(self):
        if self._is_connected or not self.page:
            return

        def _pulse_loop():
            grow = True
            while not self._is_connected and self.page:
                if grow:
                    self.shadow.blur_radius = 50
                    self.shadow.spread_radius = 5
                    self.shadow.color = ft.Colors.with_opacity(0.8, "#fbbf24")
                    self.border = ft.border.all(4, ft.Colors.with_opacity(0.8, "#fbbf24"))
                else:
                    self.shadow.blur_radius = 20
                    self.shadow.spread_radius = 1
                    self.shadow.color = ft.Colors.with_opacity(0.4, "#fbbf24")
                    self.border = ft.border.all(2, ft.Colors.with_opacity(0.5, "#fbbf24"))
                
                self.update()
                grow = not grow
                import time
                time.sleep(1.0) # Slow breath
        
        import threading
        threading.Thread(target=_pulse_loop, daemon=True).start()

