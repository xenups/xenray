"""Settings drawer component."""
import flet as ft
import os

# Imports assumed to be available in your project structure
from src.core.config_manager import ConfigManager
from src.core.types import ConnectionMode
from src.utils.process_utils import ProcessUtils
# ASSETS_DIR is needed for checking Geo files, so it's included here.
# Assuming 'src.core.constants' is where ASSETS_DIR is defined.
from src.core.constants import ASSETS_DIR 


class SettingsDrawer(ft.NavigationDrawer):
    """Settings drawer component."""
    
    def __init__(self, config_manager: ConfigManager, on_installer_run, on_mode_changed, get_current_mode):
        self._config_manager = config_manager
        self._on_installer_run = on_installer_run
        self._on_mode_changed = on_mode_changed
        self._get_current_mode = get_current_mode
        
        # Port configuration field
        self._port_field = ft.TextField(
            value=str(self._config_manager.get_proxy_port()),
            width=80,
            height=36,
            text_size=14,
            content_padding=8,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.CENTER,
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
        )
        
        # Mode Switch
        current_mode = self._get_current_mode()
        is_proxy = current_mode == ConnectionMode.PROXY
        
        self._mode_switch = ft.Switch(
            value=is_proxy,
            active_color=ft.Colors.PRIMARY,
            on_change=self._handle_mode_change,
        )

        # Country Dropdown
        current_country = self._config_manager.get_routing_country()
        self._country_dropdown = ft.Dropdown(
            width=120,
            text_size=13,
            content_padding=8,
            value=current_country if current_country else "none",
            options=[
                ft.dropdown.Option("none", "None"),
                ft.dropdown.Option("ir", "🇮🇷 Iran"),
                ft.dropdown.Option("cn", "🇨🇳 China"),
                ft.dropdown.Option("ru", "🇷🇺 Russia"),
            ],
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
            on_change=self._save_country
        )

        # DNS Field
        self._dns_field = ft.TextField(
            value=self._config_manager.get_custom_dns(),
            expand=True,
            height=36,
            text_size=14,
            content_padding=8,
            hint_text="8.8.8.8, 1.1.1.1",
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
        )
        
        super().__init__(
            controls=[
                ft.Container(
                    content=ft.Text("Settings", size=24, weight=ft.FontWeight.BOLD),
                    padding=ft.padding.only(left=20, top=20, bottom=15)
                ),
                
                ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT),
                
                # Connection Mode
                ft.Container(
                    content=ft.Row([
                        ft.Text("Mode", size=14, weight=ft.FontWeight.W_500),
                        ft.Row([
                            ft.Text("VPN", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                            self._mode_switch,
                            ft.Text("Proxy", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ]),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.padding.symmetric(horizontal=20, vertical=12),
                ),
                
                # Direct Country
                ft.Container(
                    content=ft.Row([
                        ft.Text("Direct Country", size=14, weight=ft.FontWeight.W_500),
                        self._country_dropdown
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.padding.symmetric(horizontal=20, vertical=12),
                ),

                # DNS
                ft.Container(
                    content=ft.Row([
                        ft.Text("DNS", size=14, weight=ft.FontWeight.W_500),
                        ft.Row([
                            self._dns_field,
                            ft.IconButton(
                                icon=ft.Icons.SAVE_OUTLINED,
                                icon_size=18,
                                icon_color=ft.Colors.PRIMARY,
                                on_click=self._save_dns
                            )
                        ], expand=True)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.padding.symmetric(horizontal=20, vertical=12),
                ),

                # SOCKS Port
                ft.Container(
                    content=ft.Row([
                        ft.Text("SOCKS Port", size=14, weight=ft.FontWeight.W_500),
                        ft.Row([
                            self._port_field,
                            ft.IconButton(
                                icon=ft.Icons.SAVE_OUTLINED,
                                icon_size=18,
                                icon_color=ft.Colors.PRIMARY,
                                on_click=self._save_port
                            )
                        ])
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.padding.symmetric(horizontal=20, vertical=12),
                ),

                ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.5),
                
                # Updates
                ft.Container(
                    content=ft.Column([
                        ft.Text("Updates", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                        ft.Container(height=8),
                        self._build_update_button("Xray Core", "xray"),
                        ft.Container(height=8),
                        self._build_update_button("Geo Files", "geo"),
                    ]),
                    padding=ft.padding.symmetric(horizontal=20, vertical=12),
                ),
                
                ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.5),

                # About
                ft.Container(
                    content=ft.Column([
                        ft.Text("XenRay v1.0.0", size=14, weight=ft.FontWeight.BOLD),
                        ft.Text("by Xenups", size=12, color=ft.Colors.PRIMARY),
                    ]),
                    padding=ft.padding.symmetric(horizontal=20, vertical=12),
                ),
            ],
            bgcolor=ft.Colors.SURFACE,
            surface_tint_color=ft.Colors.SURFACE_TINT,
        )

    def _build_update_button(self, label, component):
        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, size=16, color=ft.Colors.ON_PRIMARY_CONTAINER),
                ft.Text(label, size=12, color=ft.Colors.ON_PRIMARY_CONTAINER, weight=ft.FontWeight.W_500),
            ], alignment=ft.MainAxisAlignment.CENTER),
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            padding=10,
            border_radius=8,
            on_click=lambda e: self._on_installer_run(component),
            ink=True,
            expand=True,
        )

    def _handle_mode_change(self, e):
        is_proxy = self._mode_switch.value
        
        if not is_proxy:
            if not ProcessUtils.is_admin():
                # Revert switch value because admin privileges are required for VPN mode
                self._mode_switch.value = True
                self._mode_switch.update()
                
                # Notify user about admin requirement using Snackbar pattern
                page = self._mode_switch.page
                if page:
                    page.open(ft.SnackBar(
                        content=ft.Text("Admin privileges required for VPN mode."),
                        bgcolor=ft.colors.RED_700
                    ))
                    
                self._on_mode_changed(ConnectionMode.VPN) 
                return

        new_mode = ConnectionMode.PROXY if is_proxy else ConnectionMode.VPN
        self._on_mode_changed(new_mode)

    def _save_port(self, e):
        page = self._port_field.page
        if not page:
            self._port_field.error_text = "Page context missing."
            self._port_field.update()
            return
            
        try:
            port = int(self._port_field.value)
            if 1024 <= port <= 65535:
                self._config_manager.set_proxy_port(port)
                self._port_field.error_text = ""
                
                # --- FIX: Using page.open() ---
                page.open(ft.SnackBar(
                    content=ft.Text(f"SOCKS Port saved: {port} 💾")
                ))
            else:
                self._port_field.error_text = "1024-65535"
                page.open(ft.SnackBar(
                    content=ft.Text("Invalid Port Range! (1024-65535)"),
                    bgcolor=ft.colors.RED_700
                ))
        except ValueError:
            self._port_field.error_text = "Invalid"
            page.open(ft.SnackBar(
                content=ft.Text("Invalid Port Format! Must be a number."),
                bgcolor=ft.colors.RED_700
            ))
        
        self._port_field.update()
        page.update() 
        
    def _save_country(self, e):
        page = self._country_dropdown.page
        if not page:
            return
            
        val = self._country_dropdown.value
        
        if val != "none":
            geoip_path = os.path.join(ASSETS_DIR, "geoip.dat")
            geosite_path = os.path.join(ASSETS_DIR, "geosite.dat")
            
            if not os.path.exists(geoip_path) or not os.path.exists(geosite_path):
                # --- FIX: Using page.open() ---
                page.open(ft.SnackBar(
                    content=ft.Text("Geo files missing!"),
                    action="Update",
                    on_action=lambda e: self._on_installer_run("geo")
                ))
                # Note: Continue saving the configuration even if files are missing
        
        self._config_manager.set_routing_country(val)
        
        # --- FIX: Using page.open() ---
        page.open(ft.SnackBar(
            content=ft.Text(f"Direct Country saved to: {val} 🌐")
        ))
        page.update()

    def _save_dns(self, e):
        page = self._dns_field.page
        if not page:
            return
            
        val = self._dns_field.value
        self._config_manager.set_custom_dns(val)
        
        # --- FIX: Using page.open() ---
        page.open(ft.SnackBar(
            content=ft.Text("Custom DNS saved successfully. ✅")
        ))
        page.update()