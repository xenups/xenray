import flet as ft


class ConnectionButton(ft.Container):
    """Connection button with animated glow based on network activity."""

    def __init__(self, on_click):
        self._icon = ft.Icon(ft.Icons.POWER_SETTINGS_NEW, size=54, color=ft.Colors.WHITE)
        self._is_connected = False
        self._is_connecting = False
        self._current_activity = 0
        self._last_active = False
        self._state = "disconnected"  # Track state: disconnected, connecting, connected

        # Outer glow layer - breathing glow area (~210px)
        self._glow_layer = ft.Container(
            width=210,  # Button is 180, so 15px glow space on each side
            height=210,
            border_radius=105,
            bgcolor=ft.Colors.TRANSPARENT,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=24,
                color=ft.Colors.with_opacity(0.2, ft.Colors.BLACK),
                offset=ft.Offset(0, 0),
            ),
            opacity=1.0,  # Animated opacity for network activity visibility
            animate_opacity=800,  # Smooth fade for network changes
            animate_scale=ft.Animation(800, ft.AnimationCurve.EASE_IN_OUT),  # Smooth scaling
            animate=ft.Animation(600, ft.AnimationCurve.EASE_IN_OUT),  # Smooth shadow/color changes
        )

        # Inner button (the actual clickable glass button)
        self._button = ft.Container(
            content=self._icon,
            width=180,
            height=180,
            border_radius=90,
            bgcolor="#1e293b",
            border=ft.Border.all(1.5, ft.Colors.with_opacity(0.2, ft.Colors.WHITE)),
            on_click=on_click,
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
            width=210,  # Match glow layer
            height=210,
            alignment=ft.Alignment.CENTER,
        )

    def update_theme(self, is_dark: bool):
        """Update button appearance based on theme."""
        if self._is_connected or self._is_connecting:
            return

        # Keep it glassy regardless of theme, just adjust tint
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
        self._state = "connected"  # Track current state

        # Purple Glass Style for button
        self._button.bgcolor = ft.Colors.with_opacity(0.25, "#8b5cf6")
        self._button.border = ft.Border.all(2.5, ft.Colors.with_opacity(0.5, "#a78bfa"))
        self._icon.color = ft.Colors.WHITE
        self._button.update()

        # Reset glow layer for network activity animation
        self._glow_layer.opacity = 1.0
        self._glow_layer.scale = 1.0

        # Outer glow - tight purple glow
        self._glow_layer.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=30,
            color=ft.Colors.with_opacity(0.7, "#8b5cf6"),
            offset=ft.Offset(0, 0),
        )
        self._glow_layer.update()

        # Start a gentle idle breathing pulse for the connected state
        # This keeps the button "alive" even when waiting for first network stats
        try:
            _has_page = self.page is not None
        except RuntimeError:
            _has_page = False
        if _has_page:
            import asyncio

            async def _connected_breath():
                grow = True
                while self._state == "connected":
                    try:
                        _ = self.page
                    except RuntimeError:
                        break
                    try:
                        # Only pulse if network activity is low (idle breath)
                        # High activity will override with more dramatic expansion in update_network_activity
                        if self._current_activity < 5:
                            if grow:
                                self._glow_layer.opacity = 0.8
                                self._glow_layer.scale = 1.02
                            else:
                                self._glow_layer.opacity = 0.5
                                self._glow_layer.scale = 1.0
                            self._glow_layer.update()

                        grow = not grow
                        await asyncio.sleep(1.2)  # Slower, calmer breath for connected idle
                    except Exception:
                        break

                    try:
                        # Only pulse if network activity is low (idle breath)
                        # High activity will override with more dramatic expansion in update_network_activity
                        if self._current_activity < 5:
                            if grow:
                                self._glow_layer.opacity = 0.8
                                self._glow_layer.scale = 1.02
                            else:
                                self._glow_layer.opacity = 0.5
                                self._glow_layer.scale = 1.0
                            self._glow_layer.update()

                        grow = not grow
                        await asyncio.sleep(1.2)  # Slower, calmer breath for connected idle
                    except Exception:
                        break

            self.page.run_task(_connected_breath)

    def set_disconnected(self):
        """Set button to disconnected state."""
        self._is_connected = False
        self._is_connecting = False
        self._state = "disconnected"
        self._current_activity = 0

        # Revert button to standard glass
        self._button.bgcolor = ft.Colors.with_opacity(0.15, "#1e293b")
        self._button.border = ft.Border.all(1.5, ft.Colors.with_opacity(0.2, ft.Colors.WHITE))
        self._icon.color = ft.Colors.WHITE
        self._button.update()

        # Minimal glow
        self._glow_layer.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=20,
            color=ft.Colors.with_opacity(0.15, ft.Colors.BLACK),
            offset=ft.Offset(0, 0),
        )
        self._glow_layer.update()

    def set_connecting(self):
        """Set connecting state with subtle amber glass pulse."""
        self._is_connected = False
        self._is_connecting = True
        self._state = "connecting"

        # Amber Glass Style for button
        self._button.bgcolor = ft.Colors.with_opacity(0.25, "#f59e0b")
        self._button.border = ft.Border.all(2.5, ft.Colors.with_opacity(0.5, "#fbbf24"))
        self._icon.color = ft.Colors.WHITE
        self._button.update()

        self._glow_layer.opacity = 1.0
        self._glow_layer.scale = 1.0

        self._glow_layer.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=28,
            color=ft.Colors.with_opacity(0.35, "#f59e0b"),
            offset=ft.Offset(0, 0),
        )
        self._glow_layer.update()

        try:
            _has_page = self.page is not None
        except RuntimeError:
            _has_page = False
        if _has_page:
            import asyncio

            async def _pulse_loop():
                grow = True
                while self._is_connecting:
                    try:
                        _ = self.page
                    except RuntimeError:
                        break
                    try:
                        if grow:
                            self._glow_layer.opacity = 0.75
                            self._glow_layer.scale = 1.02
                        else:
                            self._glow_layer.opacity = 0.4
                            self._glow_layer.scale = 1.0

                        self._glow_layer.update()
                        grow = not grow
                        await asyncio.sleep(0.8)
                    except Exception:
                        break

            self.page.run_task(_pulse_loop)

    def set_disconnecting(self):
        """Set disconnecting state with red glass pulse."""
        self._is_connected = False
        self._is_connecting = False
        self._state = "disconnecting"

        self._button.bgcolor = ft.Colors.with_opacity(0.25, ft.Colors.RED_700)
        self._button.border = ft.Border.all(2.5, ft.Colors.with_opacity(0.5, ft.Colors.RED_400))
        self._icon.color = ft.Colors.WHITE
        self._button.update()

        self._glow_layer.opacity = 1.0
        self._glow_layer.scale = 1.0

        self._glow_layer.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=28,
            color=ft.Colors.with_opacity(0.35, ft.Colors.RED_400),
            offset=ft.Offset(0, 0),
        )
        self._glow_layer.update()

        try:
            _has_page = self.page is not None
        except RuntimeError:
            _has_page = False
        if _has_page:
            import asyncio

            async def _disconnecting_pulse():
                grow = True
                while self._state == "disconnecting":
                    try:
                        _ = self.page
                    except RuntimeError:
                        break
                    try:
                        if grow:
                            self._glow_layer.opacity = 0.75
                            self._glow_layer.scale = 1.02
                        else:
                            self._glow_layer.opacity = 0.4
                            self._glow_layer.scale = 1.0

                        self._glow_layer.update()
                        grow = not grow
                        await asyncio.sleep(0.4)
                    except Exception:
                        break

            self.page.run_task(_disconnecting_pulse)

    def update_network_activity(self, total_bps: float):
        """
        Update glow based on network traffic (clamped blur to 35px max, spread to 4px max).
        """
        if self._state != "connected":
            return

        kb_per_sec = total_bps / 1024.0

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

        # Calculate glow parameters - strictly clamped bounds
        min_blur = 20.0
        max_blur = 35.0  # Max 35px blur prevents light bleeding
        min_spread = 0.0
        max_spread = 4.0  # Max 4px spread prevents container overlap

        blur = min_blur + (max_blur - min_blur) * (activity / 100.0)
        spread = min_spread + (max_spread - min_spread) * (activity / 100.0)
        opacity = 0.25 + 0.1 * (activity / 100.0)  # Max opacity 0.35

        # Strict clamping
        blur = max(18.0, min(35.0, blur))
        spread = max(0.0, min(4.0, spread))
        opacity = max(0.2, min(0.35, opacity))

        scale = 1.0 + (activity / 100.0) * 0.02  # 1.0 to 1.02 max scale
        glow_opacity = 0.7 + (activity / 100.0) * 0.15

        try:
            self._glow_layer.shadow = ft.BoxShadow(
                spread_radius=spread,
                blur_radius=blur,
                color=ft.Colors.with_opacity(opacity, "#8b5cf6"),
                offset=ft.Offset(0, 0),
            )
            self._glow_layer.scale = scale
            self._glow_layer.opacity = glow_opacity
            self._glow_layer.update()
        except Exception:
            pass
