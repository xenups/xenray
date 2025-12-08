import flet as ft
import asyncio
import math
import threading
import time

class SplashOverlay(ft.Container):
    """
    A stylish splash screen using Amber (Connecting) and Purple (Connected) 
    theming, with an aesthetic, theme-aware energy pulse. Compatible with Flet 0.28.3.
    """
    def __init__(self, on_cleanup):
        super().__init__(
            expand=True,
            # We start with a dark background default.
            # The actual BG color will be updated in set_page based on theme.
            bgcolor=ft.Colors.BLACK, 
            alignment=ft.alignment.center,
            animate_opacity=ft.Animation(500, ft.AnimationCurve.EASE_IN_OUT), 
            opacity=1,
        )
        self._on_cleanup = on_cleanup
        self._page = None
        self._running = True
        
        # --- APP THEME COLORS ---
        self._purple_connected = "#673AB7"  # Deep Purple for stability/connected
        self._amber_connecting = "#FFC107"  # Amber for the pulse/connecting
        self._text_color = ft.Colors.WHITE  # Default text color (will be adjusted)
        self._bg_color = ft.Colors.BLACK    # Default background color

        # 1. Audio Pulse Container (The fading, blurry, breathing effect)
        self._audio_pulse_container = ft.Container(
            width=200,
            height=200,
            border_radius=100,
            # The gradient uses Amber for the core pulse
            gradient=ft.RadialGradient(
                colors=[
                    ft.Colors.with_opacity(0.8, self._amber_connecting), # Amber core
                    ft.Colors.with_opacity(0.4, self._purple_connected), # Transition to Purple
                    ft.Colors.with_opacity(0.0, ft.Colors.BLACK),        # Fade to BG (will be updated)
                ],
                stops=[0.0, 0.5, 1.0],
            ),
            blur=ft.Blur(4, 4, ft.BlurTileMode.CLAMP), 
            scale=ft.Scale(1.0),
        )
        
        # 2. Central Shield Icon (Static and stable)
        self._icon = ft.Icon(
            ft.Icons.SHIELD_ROUNDED, 
            size=100,
            color=self._purple_connected, # Stable Purple color
            opacity=1.0,
        )
        
        # Title text 
        self._title_text = ft.Text(
            "XenRay",
            size=52, 
            weight=ft.FontWeight.W_900, 
            color=self._text_color, 
            opacity=1.0,
        )
        
        # Subtitle text (loader)
        self._subtitle_text = ft.Text(
            "Initializing...",
            size=15,
            color=ft.Colors.GREY_500, 
            opacity=0.8,
        )

        # Main content layout (Stack the glow behind the icon)
        self.content = ft.Column(
            [
                ft.Stack(
                    [
                        self._audio_pulse_container, 
                        self._icon,                  
                    ],
                    width=200,
                    height=200,
                    alignment=ft.alignment.center,
                ),
                ft.Container(height=25), 
                self._title_text,
                ft.Container(height=10), 
                self._subtitle_text,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        
        self._start_breathing_pulse()

# --- Methods for Page Management and Animation Control ---

    def set_page(self, page):
        """
        Sets the page reference and adjusts colors based on the current theme mode.
        """
        self._page = page
        
        # Determine Theme-aware colors
        is_dark = page.theme_mode == ft.ThemeMode.DARK
        
        if is_dark:
            # Dark Mode: Dark BG, White Text
            self._bg_color = ft.Colors.BLACK
            self._text_color = ft.Colors.WHITE
        else:
            # Light Mode: White/Surface BG, Black Text
            self._bg_color = ft.Colors.WHITE
            self._text_color = ft.Colors.BLACK
            
        # Apply colors to the container and texts
        self.bgcolor = self._bg_color
        self._title_text.color = self._text_color
        
        # Update the gradient's fade-out color to match the new background
        self._audio_pulse_container.gradient.colors = [
            ft.Colors.with_opacity(0.8, self._amber_connecting),
            ft.Colors.with_opacity(0.4, self._purple_connected),
            ft.Colors.with_opacity(0.0, self._bg_color), # Fade to the determined BG color
        ]
        
        # Force a quick update to apply new static colors immediately
        if self._page:
             self._page.update()


    def _start_breathing_pulse(self):
        """
        Creates a smooth, outward-fading pulse using the Amber/Purple theme.
        """
        def _anim_loop():
            start_time = time.time()
            while self._running and self.opacity > 0:
                try:
                    elapsed = time.time() - start_time
                    # Single pulse: 0 to 1 over ~2.0 seconds (rate 1.5)
                    pulse = (math.sin(elapsed * 1.5) + 1) / 2 
                    
                    # 1. Pulse the Container Scale (Audio wave effect)
                    scale_val = 1.0 + (pulse * 0.35)
                    self._audio_pulse_container.scale = ft.Scale(scale_val)

                    # 2. Pulse the Blur Radius 
                    blur_val = 4 + (pulse * 8)
                    self._audio_pulse_container.blur.sigma_x = blur_val
                    self._audio_pulse_container.blur.sigma_y = blur_val
                    
                    # 3. Subtle Text Fade/Shimmer
                    self._title_text.opacity = 0.9 + (pulse * 0.1)
                    self._subtitle_text.opacity = 0.7 + (pulse * 0.3)

                    if self._page:
                        self._page.update()
                    
                except Exception:
                    break
                time.sleep(0.03) 
        
        threading.Thread(target=_anim_loop, daemon=True).start()


    async def fade_out(self):
        """Performs the controlled fade-out and calls the cleanup function."""
        await asyncio.sleep(2.0)  
        
        self._running = False
        
        self.opacity = 0
        if self._page:
            self._page.update()
            
        await asyncio.sleep(0.6)  
        
        self._on_cleanup(self)