import flet as ft
import asyncio

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
        
        # Icon with separate glow container
        self._glow_container = ft.Container(
             width=100, height=100, border_radius=50,
             bgcolor=ft.Colors.PRIMARY,
             opacity=0.2,
             animate=ft.Animation(1000, ft.AnimationCurve.EASE_IN_OUT),
        )

        self.content = ft.Column(
            [
                ft.Stack(
                    [
                        self._glow_container,
                        ft.Container(
                            content=ft.Icon(ft.Icons.SHIELD_MOON, size=60, color=ft.Colors.PRIMARY),
                            alignment=ft.alignment.center,
                            width=100, height=100,
                        ),
                    ],
                    alignment=ft.alignment.center
                ),
                ft.Text("XenRay", size=40, weight=ft.FontWeight.BOLD),
                ft.Container(height=20),
                ft.Text("Initializing...", size=12, color=ft.Colors.OUTLINE)
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        
        # Start breathing animation
        self._start_breathing()

    def _start_breathing(self):
        import threading
        import time
        def _anim_loop():
             grow = True
             # Loop while we are attached to page or just started (has opacity)
             while self.opacity > 0:
                 try:
                     # Check if we are still relevant (simplistic: opacity check)
                     if grow:
                         self._glow_container.width = 120
                         self._glow_container.height = 120
                         self._glow_container.opacity = 0.4
                     else:
                         self._glow_container.width = 100
                         self._glow_container.height = 100
                         self._glow_container.opacity = 0.2
                     self._glow_container.update()
                     grow = not grow
                 except:
                     # Stop loop if update fails (e.g. unmounted)
                     break
                 time.sleep(1.0)
        
        threading.Thread(target=_anim_loop, daemon=True).start()

    def start_animation(self):
        """Fade out and remove self."""
        # This should be called by the page after some initialization
        # self.page.run_task(self._fade_out)
        pass 
        
    async def fade_out(self):
        await asyncio.sleep(1.5) # Minimum splash time
        self.opacity = 0
        self.update()
        await asyncio.sleep(0.5) # Wait for fade
        self._on_cleanup(self)
