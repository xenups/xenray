import flet as ft


class ConnectionButton(ft.Container):
    """Connection button with animated glow based on network activity."""

    def __init__(self, on_click):
        self._icon = ft.Icon(ft.Icons.POWER_SETTINGS_NEW, size=55, color=ft.Colors.WHITE)
        self._is_connected = False
        self._is_connecting = False
        self._current_activity = 0
        self._last_active = False
        self._state = "disconnected"  # Track state: disconnected, connecting, connected, disconnecting

        # Outer glow layer - very tight, minimal space for glow
        self._glow_layer = ft.Container(
            width=190,  # Button is 170, so 10px glow space on each side
            height=190,
            border_radius=95,
            bgcolor=ft.Colors.TRANSPARENT,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=20,
                color=ft.Colors.with_opacity(0.2, ft.Colors.BLACK),
                offset=ft.Offset(0, 0),
            ),
            opacity=1.0,
            animate_opacity=800,
            animate_scale=ft.Animation(800, ft.AnimationCurve.EASE_IN_OUT),
            animate=ft.Animation(600, ft.AnimationCurve.EASE_IN_OUT),
        )

        def _on_button_click(e):
            if self._state == "disconnecting":
                return
            if on_click:
                on_click(e)

        # Inner button (the actual clickable glass button)
        self._button = ft.Container(
            content=self._icon,
            width=170,
            height=170,
            border_radius=85,
            bgcolor="#1e293b",
            border=ft.Border.all(1.5, ft.Colors.with_opacity(0.2, ft.Colors.WHITE)),
            on_click=_on_button_click,
            alignment=ft.Alignment.CENTER,
        )

        # Stack: glow behind, button on top
        super().__init__(
            content=ft.Stack(
                [
                    self._glow_layer,
                    self._button,
                ],
                alignment=ft.Alignment.CENTER,
            ),
            width=190,
            height=190,
            alignment=ft.Alignment.CENTER,
        )

    def _safe_update(self, control):
        try:
            control.update()
        except Exception:
            pass

    def _get_page_safe(self):
        """Safely retrieve Flet page instance without raising RuntimeError."""
        try:
            if self.page:
                return self.page
        except Exception:
            pass
        try:
            if self._button.page:
                return self._button.page
        except Exception:
            pass
        try:
            if self._glow_layer.page:
                return self._glow_layer.page
        except Exception:
            pass
        return None

    def update_theme(self, is_dark: bool):
        """Update button appearance based on theme."""
        if self._is_connected or self._is_connecting:
            return

        if is_dark:
            self._button.bgcolor = ft.Colors.with_opacity(0.15, "#1e293b")
            self._button.border = ft.Border.all(1.5, ft.Colors.with_opacity(0.2, ft.Colors.WHITE))
        else:
            self._button.bgcolor = ft.Colors.with_opacity(0.15, ft.Colors.WHITE)
            self._button.border = ft.Border.all(1.5, ft.Colors.with_opacity(0.3, ft.Colors.BLACK12))

        try:
            self._button.update()
        except RuntimeError:
            pass

    def set_connected(self):
        """Set button to connected state with subtle purple glass glow."""
        self._is_connected = True
        self._is_connecting = False
        self._state = "connected"

        # Deep Apple Purple Glass Style for button
        self._button.bgcolor = ft.Colors.with_opacity(0.3, "#6d28d9")
        self._button.border = ft.Border.all(2.5, ft.Colors.with_opacity(0.5, "#7c3aed"))
        self._icon.color = ft.Colors.WHITE
        self._safe_update(self._button)

        # Reset glow layer for network activity animation
        self._glow_layer.opacity = 1.0
        self._glow_layer.scale = 1.0

        # Outer glow - elegant, balanced Apple-style deep purple gradient halo
        self._glow_layer.shadow = ft.BoxShadow(
            spread_radius=2,
            blur_radius=36,
            color=ft.Colors.with_opacity(0.55, "#6d28d9"),
            offset=ft.Offset(0, 0),
        )
        self._safe_update(self._glow_layer)

        # Start a gentle idle breathing pulse for the connected state
        pg = self._get_page_safe()
        if pg:
            import asyncio

            async def _connected_breath():
                grow = True
                while self._state == "connected":
                    if not self._get_page_safe():
                        break
                    try:
                        if self._current_activity < 5:
                            if grow:
                                self._glow_layer.opacity = 0.8
                                self._glow_layer.scale = 1.02
                            else:
                                self._glow_layer.opacity = 0.5
                                self._glow_layer.scale = 1.0
                            self._safe_update(self._glow_layer)

                        grow = not grow
                        await asyncio.sleep(1.2)
                    except Exception:
                        break

            try:
                pg.run_task(_connected_breath)
            except Exception:
                pass

    def set_disconnected(self):
        """Reset button to idle disconnected state."""
        self._is_connected = False
        self._is_connecting = False
        self._state = "disconnected"
        self._current_activity = 0

        # Revert button to standard glass
        self._button.bgcolor = ft.Colors.with_opacity(0.15, "#1e293b")
        self._button.border = ft.Border.all(1.5, ft.Colors.with_opacity(0.2, ft.Colors.WHITE))
        self._icon.color = ft.Colors.WHITE
        self._safe_update(self._button)

        # Minimal glow
        self._glow_layer.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=20,
            color=ft.Colors.with_opacity(0.2, ft.Colors.BLACK),
            offset=ft.Offset(0, 0),
        )
        self._glow_layer.scale = 1.0
        self._glow_layer.opacity = 1.0
        self._safe_update(self._glow_layer)

    def set_connecting(self):
        """Set connecting state with subtle amber glass pulse."""
        self._is_connected = False
        self._is_connecting = True
        self._state = "connecting"

        # Amber Glass Style for button
        self._button.bgcolor = ft.Colors.with_opacity(0.25, "#f59e0b")
        self._button.border = ft.Border.all(2.5, ft.Colors.with_opacity(0.5, "#fbbf24"))
        self._icon.color = ft.Colors.WHITE
        self._safe_update(self._button)

        # Reset glow layer for smooth connecting animation
        self._glow_layer.opacity = 1.0
        self._glow_layer.scale = 1.0

        # Outer glow - tight amber
        self._glow_layer.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=35,
            color=ft.Colors.with_opacity(0.5, "#f59e0b"),
            offset=ft.Offset(0, 0),
        )
        self._safe_update(self._glow_layer)

        # Start async pulse loop
        pg = self._get_page_safe()
        if pg:
            import asyncio

            async def _pulse_loop():
                grow = True
                while self._is_connecting:
                    if not self._get_page_safe():
                        break
                    try:
                        if grow:
                            self._glow_layer.opacity = 0.8
                            self._glow_layer.scale = 1.04
                        else:
                            self._glow_layer.opacity = 0.4
                            self._glow_layer.scale = 1.0

                        self._safe_update(self._glow_layer)
                        grow = not grow
                        await asyncio.sleep(0.8)
                    except Exception:
                        break

            try:
                pg.run_task(_pulse_loop)
            except Exception:
                pass

    def set_disconnecting(self):
        """Set disconnecting state with red glass pulse."""
        self._is_connected = False
        self._is_connecting = False
        self._state = "disconnecting"

        # Red Glass Style for button
        self._button.bgcolor = ft.Colors.with_opacity(0.25, ft.Colors.RED_700)
        self._button.border = ft.Border.all(2.5, ft.Colors.with_opacity(0.5, ft.Colors.RED_400))
        self._icon.color = ft.Colors.WHITE
        self._safe_update(self._button)

        # Reset glow layer for smooth animation
        self._glow_layer.opacity = 1.0
        self._glow_layer.scale = 1.0

        # Outer glow - tight red
        self._glow_layer.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=35,
            color=ft.Colors.with_opacity(0.5, ft.Colors.RED_400),
            offset=ft.Offset(0, 0),
        )
        self._safe_update(self._glow_layer)

        # Start async pulse loop
        pg = self._get_page_safe()
        if pg:
            import asyncio

            async def _disconnecting_pulse():
                grow = True
                while self._state == "disconnecting":
                    if not self._get_page_safe():
                        break
                    try:
                        if grow:
                            self._glow_layer.opacity = 0.8
                            self._glow_layer.scale = 1.04
                        else:
                            self._glow_layer.opacity = 0.4
                            self._glow_layer.scale = 1.0

                        self._safe_update(self._glow_layer)
                        grow = not grow
                        await asyncio.sleep(0.4)  # Faster pulse for disconnecting
                    except Exception:
                        break

            try:
                pg.run_task(_disconnecting_pulse)
            except Exception:
                pass

    def update_network_activity(self, total_bps: float):
        """Update the glow based on real-time network activity (only when connected)."""
        if self._state != "connected":
            return

        kb_per_sec = total_bps / 1024

        if kb_per_sec < 10:
            activity = int(kb_per_sec * 1)
        elif kb_per_sec < 50:
            activity = int(10 + (kb_per_sec / 50) * 25)
        elif kb_per_sec < 500:
            activity = int(35 + ((kb_per_sec - 50) / 450) * 30)
        elif kb_per_sec < 2000:
            activity = int(65 + ((kb_per_sec - 500) / 1500) * 25)
        else:
            activity = min(100, int(90 + (kb_per_sec / 10000) * 10))

        if abs(activity - self._current_activity) < 2:
            return

        self._current_activity = activity

        min_blur = 28
        max_blur = 48
        min_spread = 1
        max_spread = 4

        blur = min_blur + (max_blur - min_blur) * (activity / 100)
        spread = min_spread + (max_spread - min_spread) * (activity / 100)
        opacity = 0.5 + 0.25 * (activity / 100)

        blur = max(25, min(52, blur))
        spread = max(1, min(5, spread))
        opacity = max(0.45, min(0.75, opacity))

        scale = 1.0 + (activity / 100) * 0.05
        glow_opacity = 0.7 + (activity / 100) * 0.3

        try:
            self._glow_layer.shadow = ft.BoxShadow(
                spread_radius=spread,
                blur_radius=blur,
                color=ft.Colors.with_opacity(opacity * 0.75, "#6d28d9"),
                offset=ft.Offset(0, 0),
            )
            self._glow_layer.scale = scale
            self._glow_layer.opacity = glow_opacity
            self._safe_update(self._glow_layer)
        except Exception:
            pass
