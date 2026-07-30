import flet as ft


class ConnectionButton(ft.Container):
    """Balanced Glassmorphism Connection Button."""

    def __init__(self, on_click):
        self._icon = ft.Icon(
            ft.Icons.POWER_SETTINGS_NEW, size=60, color=ft.Colors.WHITE
        )

        self._is_connected = False
        self._is_connecting = False
        self._current_activity = 0
        self._state = "disconnected"

        def _on_button_click(e):
            if self._state == "disconnecting":
                return
            if on_click:
                on_click(e)

        super().__init__(
            content=self._icon,
            width=180,
            height=180,
            border_radius=90,
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.WHITE),
            border=ft.Border.all(1.5, ft.Colors.with_opacity(0.25, ft.Colors.WHITE)),
            on_click=_on_button_click,
            alignment=ft.Alignment.CENTER,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=24,
                color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK),
                offset=ft.Offset(0, 8),
            ),
            animate=ft.Animation(300, ft.AnimationCurve.EASE_OUT_QUAD),
        )

    def _safe_update(self, control=None):
        try:
            if control:
                control.update()
            elif self.page:
                self.update()
        except Exception:
            pass

    def update_theme(self, is_dark: bool):
        """Maintain glassmorphism appearance based on theme."""
        if self._is_connected or self._is_connecting:
            return
        if is_dark:
            self.bgcolor = ft.Colors.with_opacity(0.12, ft.Colors.WHITE)
            self.border = ft.Border.all(
                1.5, ft.Colors.with_opacity(0.25, ft.Colors.WHITE)
            )
        else:
            self.bgcolor = ft.Colors.with_opacity(0.15, ft.Colors.WHITE)
            self.border = ft.Border.all(
                1.5, ft.Colors.with_opacity(0.3, ft.Colors.BLACK12)
            )
        self._safe_update()

    def set_connected(self):
        """Set connected state with purple glassmorphism styling."""
        self._is_connected = True
        self._is_connecting = False
        self._state = "connected"

        self.bgcolor = ft.Colors.with_opacity(0.28, "#7c3aed")
        self.border = ft.Border.all(2.0, ft.Colors.with_opacity(0.65, "#c084fc"))
        self._icon.color = ft.Colors.WHITE
        self.shadow = ft.BoxShadow(
            spread_radius=2,
            blur_radius=32,
            color=ft.Colors.with_opacity(0.5, "#7c3aed"),
            offset=ft.Offset(0, 8),
        )
        self._safe_update()

    def set_disconnected(self):
        """Reset button to idle glassmorphism state."""
        self._is_connected = False
        self._is_connecting = False
        self._state = "disconnected"
        self._current_activity = 0

        self.bgcolor = ft.Colors.with_opacity(0.12, ft.Colors.WHITE)
        self.border = ft.Border.all(1.5, ft.Colors.with_opacity(0.25, ft.Colors.WHITE))
        self._icon.color = ft.Colors.WHITE
        self.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=24,
            color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK),
            offset=ft.Offset(0, 8),
        )
        self._safe_update()

    def set_connecting(self):
        """Set connecting state with amber glassmorphism pulse."""
        self._is_connected = False
        self._is_connecting = True
        self._state = "connecting"

        self.bgcolor = ft.Colors.with_opacity(0.25, "#f59e0b")
        self.border = ft.Border.all(2.0, ft.Colors.with_opacity(0.65, "#fbbf24"))
        self.shadow = ft.BoxShadow(
            spread_radius=2,
            blur_radius=32,
            color=ft.Colors.with_opacity(0.5, "#f59e0b"),
            offset=ft.Offset(0, 8),
        )
        self._safe_update()

    def set_disconnecting(self):
        """Set disconnecting state with red glassmorphism pulse."""
        self._is_connected = False
        self._is_connecting = False
        self._state = "disconnecting"

        self.bgcolor = ft.Colors.with_opacity(0.25, "#f43f5e")
        self.border = ft.Border.all(2.0, ft.Colors.with_opacity(0.65, "#fb7185"))
        self.shadow = ft.BoxShadow(
            spread_radius=2,
            blur_radius=32,
            color=ft.Colors.with_opacity(0.5, "#f43f5e"),
            offset=ft.Offset(0, 8),
        )
        self._safe_update()

    def update_network_activity(self, total_bps: float):
        """Update glass glow dynamic intensity based on throughput."""
        if self._state != "connected":
            return

        kb_per_sec = total_bps / 1024
        activity = min(100, int(kb_per_sec / 10))

        if abs(activity - self._current_activity) < 2:
            return

        self._current_activity = activity
        blur = 30 + (activity / 100) * 18
        spread = 2 + (activity / 100) * 3

        try:
            self.shadow = ft.BoxShadow(
                spread_radius=spread,
                blur_radius=blur,
                color=ft.Colors.with_opacity(0.55, "#c084fc"),
                offset=ft.Offset(0, 8),
            )
            self._safe_update()
        except Exception:
            pass
