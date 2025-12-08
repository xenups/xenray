"""Status display component for showing connection status."""

import threading
import time
import urllib.error
import urllib.request

import flet as ft


class StatusDisplay(ft.Container):
    """Displays connection status - step text during connecting, ping after connected."""

    def __init__(self):
        self._msg_text = ft.Text(
            "",
            size=14,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.RIGHT,
            weight=ft.FontWeight.W_500,
        )
        self._dots_text = ft.Text(
            "",
            size=14,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.LEFT,
            weight=ft.FontWeight.W_500,
            width=20, # Fixed width for dots area
            visible=False,
        )
        
        # Use Row to keep message static while dots animate
        self._content_row = ft.Row(
            [self._msg_text, self._dots_text],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=0,
            tight=True,
        )

        super().__init__(
            content=self._content_row,
            padding=5,
        )

    def set_status(self, message: str, color=None):
        """Set custom status message."""
        self._msg_text.value = message
        self._dots_text.value = "" # Clear dots
        if color:
            self._msg_text.color = color
        self.update()

    def set_connecting(self, step: str = "Connecting..."):
        """Show connecting step text."""
        self._msg_text.value = step
        self._dots_text.value = ""
        self._msg_text.color = "#fbbf24"
        self.update()

    def set_step(self, step: str):
        """Update the step text during connection."""
        self._msg_text.value = step
        self.update()

    def set_initializing(self):
        """Show initializing status with animation."""
        self._msg_text.color = "#fbbf24" # Amber
        self._dots_text.color = "#fbbf24"
        self._current_msg_base = "Initializing VPN"
        
        self._dots_text.visible = True
        
        # Start animation if not running
        if not hasattr(self, "_animation_running") or not self._animation_running:
             self._animation_running = True
             threading.Thread(target=self._animate_dots, daemon=True).start()
        self.update()

    def set_connected(self, mode):
        """Show connected status only."""
        self._animation_running = False # Stop dots
        self._msg_text.value = "Connected"
        self._dots_text.value = ""
        self._dots_text.visible = False
        self._msg_text.color = "#8b5cf6" # Purple
        self.update()

    def set_disconnected(self, mode):
        """Show disconnected status (placeholder for ping)."""
        self._animation_running = False
        self._msg_text.value = "..."
        self._dots_text.value = ""
        self._dots_text.visible = False
        self._msg_text.color = ft.Colors.ON_SURFACE_VARIANT
        self.update()

    def set_pre_connection_ping(self, latency_str: str, success: bool):
        """Show ping result when disconnected."""
        if self._msg_text.value == "Initializing VPN" or self._msg_text.value == "Connected":
            return
            
        self._animation_running = False
        self._dots_text.value = ""
        self._dots_text.visible = False
        
        self._msg_text.value = f"Ping: {latency_str}"
        if success:
             # Green if < 1000ms (User request: "good ping means green is under 1000")
             self._msg_text.color = ft.Colors.GREEN_400 if "ms" in latency_str and int(latency_str.replace("ms","")) < 1000 else ft.Colors.AMBER_400
        else:
             self._msg_text.color = ft.Colors.RED_400
        self.update()

    def _animate_dots(self):
        """Animates dots for the current message base."""
        dots = 1
        
        while self._animation_running:
            if not self.page:
                break
                
            # Update base message if it changed
            if self._current_msg_base:
                self._msg_text.value = self._current_msg_base
                
            current_dots = "." * dots
            
            async def update_ui():
                if self._animation_running: 
                    self._dots_text.value = current_dots
                    self.update()
            
            try:
                self.page.run_task(update_ui)
            except:
                pass
                
            dots = (dots % 3) + 1
            time.sleep(0.4)
