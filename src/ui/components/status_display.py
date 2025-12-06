"""Status display component for showing connection status."""
import threading
import time
import urllib.error
import urllib.request

import flet as ft


class StatusDisplay(ft.Container):
    """Displays connection status - step text during connecting, ping after connected."""
    
    def __init__(self):
        self._status_text = ft.Text(
            "",
            size=14,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
            weight=ft.FontWeight.W_500,
        )
        
        super().__init__(
            content=self._status_text,
            padding=5,
        )
    
    def set_status(self, message: str, color=None):
        """Set custom status message."""
        if self._status_text:
            self._status_text.value = message
            if color:
                self._status_text.color = color
            self.update()
    
    def set_connecting(self, step: str = "Connecting..."):
        """Show connecting step text."""
        if self._status_text:
            self._status_text.value = step
            self._status_text.color = "#fbbf24"  # Amber to match button glow
            self.update()
    
    def set_step(self, step: str):
        """Update the step text during connection."""
        if self._status_text:
            self._status_text.value = step
            self.update()
    
    def set_connected(self, mode):
        """Show connected status and measure initial ping."""
        if self._status_text:
            self._status_text.value = "Connected"
            self._status_text.color = "#8b5cf6"  # Purple to match button
            self.update()
        
        # Measure ping once in background
        threading.Thread(target=self._measure_initial_ping, daemon=True).start()
    
    def set_disconnected(self, mode):
        """Show disconnected status."""
        if self._status_text:
            self._status_text.value = ""
            self._status_text.color = ft.Colors.ON_SURFACE_VARIANT
            self.update()
    
    def _measure_initial_ping(self):
        """Measure ping to google.com with retries."""
        test_url = "http://www.google.com"
        max_retries = 10
        retry_delay = 2
        
        for attempt in range(max_retries):
            if not self._status_text or not self.page:
                break
                
            try:
                start_time = time.time()
                req = urllib.request.Request(test_url, headers={'User-Agent': 'Mozilla/5.0'})
                response = urllib.request.urlopen(req, timeout=5)
                response.read()
                latency_ms = int((time.time() - start_time) * 1000)
                
                if self._status_text and self.page:
                    async def update_ping():
                        self._status_text.value = f"Ping: {latency_ms} ms"
                        self._status_text.color = "#8b5cf6"  # Purple
                        self.update()
                    
                    self.page.run_task(update_ping)
                    return
                    
            except (urllib.error.URLError, TimeoutError):
                time.sleep(retry_delay)
            except Exception:
                time.sleep(retry_delay)
        
        if self._status_text and self.page:
            async def update_failed():
                self._status_text.value = "Ping: Timeout"
                self._status_text.color = ft.Colors.RED_400
                self.update()
            self.page.run_task(update_failed)
