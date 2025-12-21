import flet as ft


class ConnectionButton(ft.Container):
    """Connection button with animated glow based on network activity."""

    def __init__(self, on_click):
        self._icon = ft.Icon(ft.Icons.POWER_SETTINGS_NEW, size=55, color=ft.Colors.WHITE)
        self._is_connected = False
        self._is_connecting = False
        self._current_activity = 0
        self._last_active = False
        self._state = "disconnected"  # Track state: disconnected, connecting, connected

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
            opacity=1.0,  # Animated opacity for network activity visibility
            animate_opacity=800,  # Smooth fade for network changes
            animate_scale=ft.Animation(800, ft.AnimationCurve.EASE_IN_OUT),  # Smooth scaling
            animate=ft.Animation(600, ft.AnimationCurve.EASE_IN_OUT),  # Smooth shadow/color changes
        )

        # Inner button (the actual clickable glass button)
        self._button = ft.Container(
            content=self._icon,
            width=170,
            height=170,
            border_radius=85,
            bgcolor=ft.Colors.with_opacity(0.15, "#1e293b"),
            blur=ft.Blur(25, 25, ft.BlurTileMode.MIRROR),
            border=ft.border.all(1.5, ft.Colors.with_opacity(0.2, ft.Colors.WHITE)),
            on_click=on_click,
            animate=ft.Animation(400, ft.AnimationCurve.EASE_OUT),
            alignment=ft.alignment.center,
        )

        # Stack: glow behind, button on top
        super().__init__(
            content=ft.Stack(
                [
                    self._glow_layer,
                    self._button,
                ],
                alignment=ft.alignment.center,
            ),
            width=190,  # Match glow layer
            height=190,
            alignment=ft.alignment.center,
        )

    def update_theme(self, is_dark: bool):
        """Update button appearance based on theme."""
        if self._is_connected or self._is_connecting:
            return

        # Keep it glassy regardless of theme, just adjust tint
        if is_dark:
            self._button.bgcolor = ft.Colors.with_opacity(0.15, "#1e293b")
            self._button.border = ft.border.all(1.5, ft.Colors.with_opacity(0.2, ft.Colors.WHITE))
        else:
            self._button.bgcolor = ft.Colors.with_opacity(0.15, ft.Colors.WHITE)
            self._button.border = ft.border.all(1.5, ft.Colors.with_opacity(0.3, ft.Colors.BLACK12))

        self._button.update()

    def set_connected(self):
        """Set button to connected state with subtle purple glass glow."""
        self._is_connected = True
        self._is_connecting = False
        self._state = "connected"  # Track current state

        # Purple Glass Style for button
        self._button.bgcolor = ft.Colors.with_opacity(0.25, "#8b5cf6")
        self._button.border = ft.border.all(2.5, ft.Colors.with_opacity(0.5, "#a78bfa"))
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
        if self.page:
            import asyncio

            async def _connected_breath():
                grow = True
                while self._state == "connected" and self.page:
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
        self._button.border = ft.border.all(1.5, ft.Colors.with_opacity(0.2, ft.Colors.WHITE))
        self._icon.color = ft.Colors.WHITE
        self._button.update()

        # Minimal glow
        self._glow_layer.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=25,
            color=ft.Colors.with_opacity(0.2, ft.Colors.BLACK),
            offset=ft.Offset(0, 0),
        )
        self._glow_layer.update()

    def set_connecting(self):
        """Set connecting state with subtle amber glass pulse."""
        self._is_connected = False
        self._is_connecting = True
        self._state = "connecting"  # Track current state

        # Amber Glass Style for button
        self._button.bgcolor = ft.Colors.with_opacity(0.25, "#f59e0b")
        self._button.border = ft.border.all(2.5, ft.Colors.with_opacity(0.5, "#fbbf24"))
        self._icon.color = ft.Colors.WHITE
        self._button.update()

        # Reset glow layer for smooth connecting animation
        self._glow_layer.opacity = 1.0
        self._glow_layer.scale = 1.0

        # Outer glow - tight amber with reduced intensity
        self._glow_layer.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=35,
            color=ft.Colors.with_opacity(0.5, "#f59e0b"),  # Reduced from 0.8
            offset=ft.Offset(0, 0),
        )
        self._glow_layer.update()

        # Start async pulse loop
        if self.page:
            import asyncio

            async def _pulse_loop():
                grow = True
                while self._is_connecting and self.page:
                    try:
                        if grow:
                            self._glow_layer.opacity = 0.8
                            self._glow_layer.scale = 1.04
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

        # Red Glass Style for button
        self._button.bgcolor = ft.Colors.with_opacity(0.25, ft.Colors.RED_700)
        self._button.border = ft.border.all(2.5, ft.Colors.with_opacity(0.5, ft.Colors.RED_400))
        self._icon.color = ft.Colors.WHITE
        self._button.update()

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
        self._glow_layer.update()

        # Start async pulse loop
        if self.page:
            import asyncio

            async def _disconnecting_pulse():
                grow = True
                while self._state == "disconnecting" and self.page:
                    try:
                        if grow:
                            self._glow_layer.opacity = 0.8
                            self._glow_layer.scale = 1.04
                        else:
                            self._glow_layer.opacity = 0.4
                            self._glow_layer.scale = 1.0

                        self._glow_layer.update()
                        grow = not grow
                        await asyncio.sleep(0.4)  # Faster pulse for disconnecting
                    except Exception:
                        break

            self.page.run_task(_disconnecting_pulse)

    def update_network_activity(self, total_bps: float):
        """
        Update the glow based on real-time network activity (only when connected).
        Args:
            total_bps: Total bytes per second (download + upload)
        """
        # Only animate network activity when in connected state
        if self._state != "connected":
            return

        kb_per_sec = total_bps / 1024

        # Map network speed to activity percentage (0-100)
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

        # Allow updates if activity changed by more than 2% for more responsive animation
        if abs(activity - self._current_activity) < 2:
            return

        self._current_activity = activity

        # Calculate glow parameters - smooth shadow breathing only
        min_blur = 25
        max_blur = 45
        min_spread = 0
        max_spread = 1

        blur = min_blur + (max_blur - min_blur) * (activity / 100)
        spread = min_spread + (max_spread - min_spread) * (activity / 100)
        opacity = 0.5 + 0.3 * (activity / 100)

        # Clamp values
        blur = max(20, min(50, blur))
        spread = max(0, min(2, spread))
        opacity = max(0.45, min(0.9, opacity))

        # Add pulsing scale and opacity for more tangible visual feedback
        scale = 1.0 + (activity / 100) * 0.05  # 1.0 to 1.05
        glow_opacity = 0.7 + (activity / 100) * 0.3  # 0.7 to 1.0

        try:
            # Update shadow (instant) and animate scale/opacity (smooth)
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
