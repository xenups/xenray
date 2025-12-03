"""Server List Component."""
import flet as ft
import socket
import time
import threading

from src.core.config_manager import ConfigManager
from src.utils.link_parser import LinkParser


class ServerList(ft.UserControl):
    """Component to manage and select servers."""
    
    def __init__(self, config_manager: ConfigManager, on_server_selected):
        super().__init__()
        self._config_manager = config_manager
        self._on_server_selected = on_server_selected
        self._profiles = []
        
    def build(self):
        # Header
        self._header = ft.Row([
            ft.Text("Servers", size=20, weight=ft.FontWeight.BOLD),
            ft.IconButton(ft.icons.ADD, on_click=self._show_add_dialog)
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        
        # List View
        self._list_view = ft.ListView(
            expand=True,
            spacing=10,
            padding=10,
        )
        
        # Add Dialog
        self._link_input = ft.TextField(
            label="VLESS Link",
            multiline=True,
            min_lines=3,
            text_size=12
        )
        self._add_dialog = ft.AlertDialog(
            title=ft.Text("Add Server"),
            content=self._link_input,
            actions=[
                ft.TextButton("Add", on_click=self._add_server),
                ft.TextButton("Cancel", on_click=self._close_dialog)
            ]
        )
        
        self._load_profiles()
        
        return ft.Container(
            content=ft.Column([
                self._header,
                ft.Divider(),
                self._list_view
            ]),
            padding=10,
            expand=True
        )
        
    def _load_profiles(self, update_ui=False):
        self._profiles = self._config_manager.load_profiles()
        
        if not hasattr(self, '_list_view'):
            return

        self._list_view.controls.clear()
        
        for profile in self._profiles:
            self._list_view.controls.append(self._create_server_item(profile))
            
        if update_ui:
            self.update()

    def _create_server_item(self, profile):
        # Extract address and port from config structure
        config = profile.get("config", {})
        outbounds = config.get("outbounds", [])
        address = "Unknown"
        port = "N/A"
        
        # Find the main server in outbounds
        for outbound in outbounds:
            protocol = outbound.get("protocol")
            if protocol in ['vless', 'vmess', 'trojan', 'shadowsocks']:
                settings = outbound.get("settings", {})
                if 'vnext' in settings and settings['vnext']:
                    server = settings['vnext'][0]
                    address = server.get('address', 'Unknown')
                    port = server.get('port', 'N/A')
                    break
                elif 'servers' in settings and settings['servers']:
                    server = settings['servers'][0]
                    address = server.get('address', 'Unknown')
                    port = server.get('port', 'N/A')
                    break
        
        ping_text = ft.Text("...", size=12, color=ft.colors.GREY_500)
        
        # Start ping in background
        threading.Thread(target=self._ping_server, args=(address, port, ping_text), daemon=True).start()

        return ft.Container(
            content=ft.Row([
                ft.Text("🌐", size=24),
                ft.Column([
                    ft.Text(profile["name"], weight=ft.FontWeight.BOLD, color=ft.colors.ON_SURFACE),
                    ft.Row([
                        ft.Text(f"{address}:{port}", size=12, color=ft.colors.ON_SURFACE_VARIANT),
                        ping_text
                    ], spacing=10),
                ], expand=True, spacing=2),
                ft.IconButton(
                    ft.icons.DELETE,
                    icon_color=ft.colors.RED_400,
                    on_click=lambda e: self._delete_server(profile["id"])
                )
            ]),
            padding=15,
            border_radius=10,
            bgcolor=ft.colors.SURFACE, # Will adapt to theme
            border=ft.border.all(1, ft.colors.OUTLINE_VARIANT),
            on_click=lambda e: self._select_server(profile),
            ink=True,
        )

    def _ping_server(self, address, port, text_control):
        if address == "Unknown" or port == "N/A":
            return
            
        max_retries = 5
        
        for i in range(max_retries):
            try:
                target_port = int(port)
                start = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((address, target_port))
                sock.close()
                
                latency = int((time.time() - start) * 1000)
                
                if result == 0:
                    text_control.value = f"{latency}ms"
                    text_control.color = ft.colors.GREEN_400
                    if text_control.page:
                        text_control.update()
                    return # Success
                
            except Exception:
                pass
            
            # Wait before retry
            time.sleep(1)
            
        # If we get here, it failed
        text_control.value = "Timeout"
        text_control.color = ft.colors.RED_400
        if text_control.page:
            text_control.update()

    def _show_add_dialog(self, e):
        self.page.dialog = self._add_dialog
        self._add_dialog.open = True
        self.page.update()
        
    def _close_dialog(self, e):
        self._add_dialog.open = False
        self.page.update()
        
    def _add_server(self, e):
        link = self._link_input.value.strip()
        if not link:
            return
            
        try:
            parsed = LinkParser.parse_vless(link)
            self._config_manager.save_profile(parsed["name"], parsed["config"])
            self._link_input.value = ""
            self._close_dialog(None)
            self._load_profiles(update_ui=True)
            
            # Auto select
            # self._select_server(parsed) 
        except Exception as ex:
            self._link_input.error_text = str(ex)
            self.update()
            
    def _delete_server(self, profile_id):
        self._config_manager.delete_profile(profile_id)
        self._load_profiles(update_ui=True)
        
    def _select_server(self, profile):
        if self._on_server_selected:
            self._on_server_selected(profile)
