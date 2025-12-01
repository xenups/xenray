"""Settings drawer component."""
import flet as ft

from src.core.config_manager import ConfigManager


class SettingsDrawer(ft.UserControl):
    """Settings drawer component."""
    
    def __init__(self, config_manager: ConfigManager, on_installer_run):
        super().__init__()
        self._config_manager = config_manager
        self._on_installer_run = on_installer_run
        self._port_field = None
        
    def build(self):
        # Port configuration field
        self._port_field = ft.TextField(
            value=str(self._config_manager.get_proxy_port()),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.CENTER,
            border_color=ft.colors.OUTLINE_VARIANT,
        )
        
        return ft.NavigationDrawer(
            controls=[
                ft.Container(height=20),
                ft.Text("Settings", size=22, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                ft.Container(height=10),
                ft.Divider(),
                
                # Settings Section
                ft.Container(
                    content=ft.Column([
                        ft.Text("Proxy Configuration", size=14, weight=ft.FontWeight.BOLD, color=ft.colors.PRIMARY),
                        ft.Row([
                            self._port_field,
                            ft.ElevatedButton(
                                "Set Port",
                                icon=ft.icons.CHECK,
                                on_click=self._save_port,
                            ),
                        ], alignment=ft.MainAxisAlignment.CENTER),
                    ]),
                    padding=15,
                    border_radius=10,
                    margin=10
                ),
                
                ft.Divider(),
                
                # About Section
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.icons.INFO_OUTLINE, color=ft.colors.PRIMARY),
                        ft.Text("About XenRay", size=18, weight=ft.FontWeight.BOLD),
                        ft.Text("Developed by Xenups", size=14, color=ft.colors.PRIMARY),
                        ft.Text("A modern, lightweight Xray client.", size=12, color=ft.colors.ON_SURFACE_VARIANT),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=20,
                    alignment=ft.alignment.center
                ),
                
                ft.Divider(),
                
                # Updates Section (at bottom, icon-only)
                ft.Container(
                    content=ft.Row([
                        ft.IconButton(
                            icon=ft.icons.DOWNLOAD,
                            tooltip="Update Xray",
                            on_click=lambda e: self._on_installer_run("xray"),
                            icon_color=ft.colors.PRIMARY
                        ),
                        ft.Text("Xray", size=12, color=ft.colors.ON_SURFACE_VARIANT),
                        ft.Container(width=20),
                        ft.IconButton(
                            icon=ft.icons.DOWNLOAD,
                            tooltip="Update Tun2Proxy",
                            on_click=lambda e: self._on_installer_run("tun2proxy"),
                            icon_color=ft.colors.PRIMARY
                        ),
                        ft.Text("Tun2Proxy", size=12, color=ft.colors.ON_SURFACE_VARIANT),
                    ], alignment=ft.MainAxisAlignment.CENTER),
                    padding=10,
                    margin=ft.margin.only(bottom=10)
                )
            ],
            bgcolor=ft.colors.SURFACE,
        )
    
    def _save_port(self, e):
        try:
            port = int(self._port_field.value)
            if 1024 <= port <= 65535:
                self._config_manager.set_proxy_port(port)
                self._port_field.error_text = ""
                # Show success feedback
                if self.page:
                    self.page.show_snack_bar(
                        ft.SnackBar(content=ft.Text(f"Port set to {port}"))
                    )
            else:
                self._port_field.error_text = "Port must be between 1024-65535"
        except ValueError:
            self._port_field.error_text = "Invalid port number"
        
        if self.page:
            self.page.update()
