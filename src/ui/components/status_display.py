"""Status display component for showing connection status."""
import threading
import time
import urllib.error
import urllib.request

import flet as ft


class StatusDisplay(ft.UserControl):
    """Displays connection status with initial ping."""
    
    def __init__(self):
        super().__init__()
        self._status_text = None
        
    def build(self):
        self._status_text = ft.Text(
            "",
            size=14,
            color=ft.colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
        )
        
        return ft.Container(
            content=self._status_text,
            padding=5,
        )
    
    def set_status(self, message: str):
        """Set custom status message."""
        if self._status_text:
            self._status_text.value = message
            self.update()
    
    def set_connecting(self):
        """Show connecting status."""
        if self._status_text:
            self._status_text.value = "Connecting..."
            self._status_text.color = ft.colors.ORANGE_400
            self.update()
    
    def set_connected(self, mode):
        """Show connected status and measure initial ping."""
        if self._status_text:
            self._status_text.value = "Connected"
            self._status_text.color = ft.colors.GREEN_400
            self.update()
        
        # Measure ping once in background
        threading.Thread(target=self._measure_initial_ping, daemon=True).start()
    
    def set_disconnected(self, mode):
        """Show disconnected status."""
        if self._status_text:
            self._status_text.value = ""
            self.update()
    
    def _measure_initial_ping(self):
        """Measure ping to google.com once."""
        test_url = "http://www.google.com"
        
        try:
            start_time = time.time()
            req = urllib.request.Request(test_url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=5)
            response.read()  # Read response to ensure full connection
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Update UI with ping result
            if self._status_text and self.page:
                async def update_ping():
                    self._status_text.value = f"Ping: {latency_ms} ms"
                    self._status_text.color = ft.colors.GREEN_400
                    self.update()
                
                self.page.run_task(update_ping)
                
        except (urllib.error.URLError, TimeoutError) as e:
            # Keep "Connected" if ping fails
            pass
        except Exception as e:
            # Keep "Connected" if ping fails
            pass
