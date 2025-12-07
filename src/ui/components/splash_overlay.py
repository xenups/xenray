import flet as ft
import asyncio
import math
import threading
import time

class SplashOverlay(ft.Container):
    def __init__(self, on_cleanup):
        super().__init__(
            expand=True,
            bgcolor=ft.Colors.SURFACE,
            alignment=ft.alignment.center,
            animate_opacity=500,
            opacity=1,
        )
        self._on_cleanup = on_cleanup
        self._page = None
        self._running = True
        
        # Purple color palette - more vibrant
        self._purple_primary = "#8b5cf6"
        self._purple_secondary = "#6d28d9"
        self._purple_dark = "#4c1d95"
        self._purple_light = "#a78bfa"
        self._purple_bright = "#c4b5fd"
        
        # Rotating ring container with gradient border effect
        self._rotating_ring = ft.Container(
            width=220,
            height=220,
            border_radius=110,
            border=ft.border.all(2, ft.Colors.with_opacity(0.4, self._purple_primary)),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=20,
                color=ft.Colors.with_opacity(0.3, self._purple_light),
                offset=ft.Offset(0, 0),
            ),
            animate_rotation=ft.Animation(3000, ft.AnimationCurve.LINEAR),
            rotate=ft.Rotate(0, alignment=ft.alignment.center),
        )
        
        # Outer pulsing circle - more visible
        self._outer_circle = ft.Container(
            width=200,
            height=200,
            border_radius=100,
            gradient=ft.RadialGradient(
                colors=[
                    ft.Colors.with_opacity(0.4, self._purple_primary),
                    ft.Colors.with_opacity(0.2, self._purple_secondary),
                    ft.Colors.with_opacity(0.0, self._purple_dark),
                ],
                stops=[0.0, 0.5, 1.0],
            ),
            shadow=ft.BoxShadow(
                spread_radius=2,
                blur_radius=50,
                color=ft.Colors.with_opacity(0.5, self._purple_primary),
                offset=ft.Offset(0, 0),
            ),
            animate=ft.Animation(2000, ft.AnimationCurve.EASE_IN_OUT),
        )
        
        # Middle pulsing circle
        self._middle_circle = ft.Container(
            width=150,
            height=150,
            border_radius=75,
            gradient=ft.RadialGradient(
                colors=[
                    ft.Colors.with_opacity(0.5, self._purple_light),
                    ft.Colors.with_opacity(0.25, self._purple_primary),
                    ft.Colors.with_opacity(0.0, self._purple_secondary),
                ],
                stops=[0.0, 0.6, 1.0],
            ),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=40,
                color=ft.Colors.with_opacity(0.6, self._purple_light),
                offset=ft.Offset(0, 0),
            ),
            animate=ft.Animation(1800, ft.AnimationCurve.EASE_IN_OUT),
        )
        
        # Inner pulsing circle
        self._inner_circle = ft.Container(
            width=110,
            height=110,
            border_radius=55,
            gradient=ft.RadialGradient(
                colors=[
                    ft.Colors.with_opacity(0.6, self._purple_primary),
                    ft.Colors.with_opacity(0.3, self._purple_secondary),
                    ft.Colors.with_opacity(0.0, self._purple_dark),
                ],
                stops=[0.0, 0.7, 1.0],
            ),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=35,
                color=ft.Colors.with_opacity(0.7, self._purple_primary),
                offset=ft.Offset(0, 0),
            ),
            animate=ft.Animation(1600, ft.AnimationCurve.EASE_IN_OUT),
        )
        
        # Icon with pulsing animation
        self._icon = ft.Icon(
            ft.Icons.SHIELD_MOON,
            size=55,
            color=self._purple_primary,
        )
        self._icon_container = ft.Container(
            content=self._icon,
            alignment=ft.alignment.center,
            width=110,
            height=110,
            animate=ft.Animation(1500, ft.AnimationCurve.EASE_IN_OUT),
            animate_opacity=ft.Animation(1500, ft.AnimationCurve.EASE_IN_OUT),
            opacity=1.0,
        )
        
        # Title text with fade animation
        self._title_text = ft.Text(
            "XenRay",
            size=42,
            weight=ft.FontWeight.BOLD,
            color=self._purple_primary,
            animate_opacity=ft.Animation(1000, ft.AnimationCurve.EASE_IN_OUT),
        )
        
        # Subtitle text
        self._subtitle_text = ft.Text(
            "Initializing...",
            size=13,
            color=ft.Colors.with_opacity(0.7, self._purple_primary),
            animate_opacity=ft.Animation(800, ft.AnimationCurve.EASE_IN_OUT),
        )

        self.content = ft.Column(
            [
                ft.Stack(
                    [
                        self._rotating_ring,
                        self._outer_circle,
                        self._middle_circle,
                        self._inner_circle,
                        self._icon_container,
                    ],
                    alignment=ft.alignment.center,
                ),
                ft.Container(height=35),
                self._title_text,
                ft.Container(height=18),
                self._subtitle_text,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        
        # Start all animations
        self._start_animations()

    def set_page(self, page):
        """Set the page reference for updates."""
        self._page = page

    def _start_animations(self):
        """Start all animation loops."""
        # Start rotating ring
        self._start_rotation()
        # Start pulsing circles
        self._start_breathing()
        # Start icon pulse
        self._start_icon_pulse()
        # Start text fade
        self._start_text_fade()

    def _start_rotation(self):
        """Continuously rotate the outer ring."""
        def _rotate_loop():
            angle = 0
            while self._running and self.opacity > 0:
                try:
                    angle = (angle + 3) % 360
                    self._rotating_ring.rotate.angle = math.radians(angle)
                    # Also pulse the ring opacity slightly
                    pulse = (math.sin(math.radians(angle * 2)) + 1) / 2
                    self._rotating_ring.border = ft.border.all(
                        2, ft.Colors.with_opacity(0.3 + (pulse * 0.2), self._purple_primary)
                    )
                    if self._page:
                        self._page.update()
                    time.sleep(0.025)  # Faster rotation
                except Exception:
                    break
        threading.Thread(target=_rotate_loop, daemon=True).start()

    def _start_breathing(self):
        """Smooth pulsing animation for circles."""
        def _anim_loop():
            start_time = time.time()
            while self._running and self.opacity > 0:
                try:
                    elapsed = time.time() - start_time
                    
                    # Outer circle: 200 to 240 (more visible range)
                    pulse1 = (math.sin(elapsed * 1.2) + 1) / 2
                    outer_size = 200 + (pulse1 * 40)
                    self._outer_circle.width = outer_size
                    self._outer_circle.height = outer_size
                    self._outer_circle.border_radius = outer_size / 2
                    # Update gradient opacity
                    new_gradient = ft.RadialGradient(
                        colors=[
                            ft.Colors.with_opacity(0.3 + (pulse1 * 0.2), self._purple_primary),
                            ft.Colors.with_opacity(0.15 + (pulse1 * 0.15), self._purple_secondary),
                            ft.Colors.with_opacity(0.0, self._purple_dark),
                        ],
                        stops=[0.0, 0.5, 1.0],
                    )
                    self._outer_circle.gradient = new_gradient
                    self._outer_circle.shadow.blur_radius = 50 + (pulse1 * 30)
                    self._outer_circle.shadow.color = ft.Colors.with_opacity(
                        0.4 + (pulse1 * 0.3), self._purple_primary
                    )
                    
                    # Middle circle: 150 to 180 (offset phase)
                    pulse2 = (math.sin(elapsed * 1.2 + 0.7) + 1) / 2
                    middle_size = 150 + (pulse2 * 30)
                    self._middle_circle.width = middle_size
                    self._middle_circle.height = middle_size
                    self._middle_circle.border_radius = middle_size / 2
                    new_gradient2 = ft.RadialGradient(
                        colors=[
                            ft.Colors.with_opacity(0.4 + (pulse2 * 0.2), self._purple_light),
                            ft.Colors.with_opacity(0.2 + (pulse2 * 0.15), self._purple_primary),
                            ft.Colors.with_opacity(0.0, self._purple_secondary),
                        ],
                        stops=[0.0, 0.6, 1.0],
                    )
                    self._middle_circle.gradient = new_gradient2
                    self._middle_circle.shadow.blur_radius = 40 + (pulse2 * 25)
                    self._middle_circle.shadow.color = ft.Colors.with_opacity(
                        0.5 + (pulse2 * 0.3), self._purple_light
                    )
                    
                    # Inner circle: 110 to 130 (different phase)
                    pulse3 = (math.sin(elapsed * 1.2 + 1.4) + 1) / 2
                    inner_size = 110 + (pulse3 * 20)
                    self._inner_circle.width = inner_size
                    self._inner_circle.height = inner_size
                    self._inner_circle.border_radius = inner_size / 2
                    new_gradient3 = ft.RadialGradient(
                        colors=[
                            ft.Colors.with_opacity(0.5 + (pulse3 * 0.2), self._purple_primary),
                            ft.Colors.with_opacity(0.25 + (pulse3 * 0.15), self._purple_secondary),
                            ft.Colors.with_opacity(0.0, self._purple_dark),
                        ],
                        stops=[0.0, 0.7, 1.0],
                    )
                    self._inner_circle.gradient = new_gradient3
                    self._inner_circle.shadow.blur_radius = 35 + (pulse3 * 20)
                    self._inner_circle.shadow.color = ft.Colors.with_opacity(
                        0.6 + (pulse3 * 0.3), self._purple_primary
                    )
                    
                    if self._page:
                        self._page.update()
                    
                except Exception:
                    break
                time.sleep(0.04)  # ~25 FPS for smooth animation
        
        threading.Thread(target=_anim_loop, daemon=True).start()

    def _start_icon_pulse(self):
        """Pulse the icon size and opacity slightly."""
        def _icon_loop():
            start_time = time.time()
            while self._running and self.opacity > 0:
                try:
                    elapsed = time.time() - start_time
                    pulse = (math.sin(elapsed * 2.0) + 1) / 2
                    # Icon size: 55 to 60
                    size = 55 + (pulse * 5)
                    self._icon.size = size
                    # Icon container opacity: 0.85 to 1.0
                    self._icon_container.opacity = 0.85 + (pulse * 0.15)
                    if self._page:
                        self._page.update()
                    time.sleep(0.05)
                except Exception:
                    break
        threading.Thread(target=_icon_loop, daemon=True).start()

    def _start_text_fade(self):
        """Fade text in and out subtly."""
        def _text_loop():
            start_time = time.time()
            while self._running and self.opacity > 0:
                try:
                    elapsed = time.time() - start_time
                    pulse = (math.sin(elapsed * 1.5) + 1) / 2
                    # Opacity: 0.7 to 1.0
                    self._title_text.opacity = 0.7 + (pulse * 0.3)
                    self._subtitle_text.opacity = 0.6 + (pulse * 0.3)
                    if self._page:
                        self._page.update()
                    time.sleep(0.06)
                except Exception:
                    break
        threading.Thread(target=_text_loop, daemon=True).start()

    def start_animation(self):
        """Fade out and remove self."""
        # This should be called by the page after some initialization
        # self.page.run_task(self._fade_out)
        pass 
        
    async def fade_out(self):
        await asyncio.sleep(2.0)  # Minimum splash time to see animations
        # Stop all animations
        self._running = False
        # Fade out
        self.opacity = 0
        if self._page:
            self._page.update()
        await asyncio.sleep(0.6)  # Wait for fade animation
        self._on_cleanup(self)
