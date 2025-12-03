"""Settings drawer component."""
import flet as ft

from src.core.config_manager import ConfigManager
from src.core.types import ConnectionMode
from src.utils.process_utils import ProcessUtils


class SettingsDrawer(ft.UserControl):
    """Settings drawer component."""
    
    def __init__(self, config_manager: ConfigManager, on_installer_run, on_mode_changed, get_current_mode):
        super().__init__()
        self._config_manager = config_manager
        self._on_installer_run = on_installer_run
        self._on_mode_changed = on_mode_changed
        self._get_current_mode = get_current_mode
        self._port_field = None
        self._mode_switch = None
        self._country_dropdown = None
        self._dns_field = None
        
    def build(self):
        # Port configuration field
        self._port_field = ft.TextField(
            value=str(self._config_manager.get_proxy_port()),
            width=100,
            height=40,
            text_size=14,
            content_padding=10,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.CENTER,
            border_color=ft.colors.OUTLINE_VARIANT,
            focused_border_color=ft.colors.PRIMARY,
        )
        
        # Mode Switch
        current_mode = self._get_current_mode()
        is_proxy = current_mode == ConnectionMode.PROXY
        
        self._mode_switch = ft.Switch(
            value=is_proxy,
            active_color=ft.colors.PRIMARY,
            on_change=self._handle_mode_change,
        )

        # Country Dropdown
        current_country = self._config_manager.get_routing_country()
        self._country_dropdown = ft.Dropdown(
            width=150,
            height=40,
            text_size=14,
            content_padding=10,
            value=current_country if current_country else "none",
            options=[
                ft.dropdown.Option("none", "None"),
                ft.dropdown.Option("ir", "🇮🇷 Iran"),
                ft.dropdown.Option("cn", "🇨🇳 China"),
                ft.dropdown.Option("ru", "🇷🇺 Russia"),
            ],
            border_color=ft.colors.OUTLINE_VARIANT,
            focused_border_color=ft.colors.PRIMARY,
            on_change=self._save_country
        )

        # DNS Field
        self._dns_field = ft.TextField(
            value=self._config_manager.get_custom_dns(),
            expand=True,
            height=40,
            text_size=14,
            content_padding=10,
            hint_text="8.8.8.8, 1.1.1.1",
            border_color=ft.colors.OUTLINE_VARIANT,
            focused_border_color=ft.colors.PRIMARY,
        )
        
        return ft.NavigationDrawer(
            controls=[
                ft.Container(
                    content=ft.Column([
                        ft.Text("Settings", size=28, weight=ft.FontWeight.BOLD),
                        ft.Text("Configure your connection", size=14, color=ft.colors.ON_SURFACE_VARIANT),
                    ]),
                    padding=ft.padding.only(left=20, top=20, bottom=10)
                ),
                
                ft.Divider(height=1, color=ft.colors.OUTLINE_VARIANT),
                
                # Connection Mode Section
                self._build_section_header("Connection Mode", ft.icons.VPN_LOCK),
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text("Proxy / VPN", size=16, weight=ft.FontWeight.W_500),
                            ft.Text("Choose connection method", size=12, color=ft.colors.ON_SURFACE_VARIANT),
                        ], expand=True),
                        ft.Row([
                            ft.Text("VPN", size=12, weight=ft.FontWeight.BOLD, color=ft.colors.ON_SURFACE_VARIANT),
                            self._mode_switch,
                            ft.Text("Proxy", size=12, weight=ft.FontWeight.BOLD, color=ft.colors.ON_SURFACE_VARIANT),
                        ], alignment=ft.MainAxisAlignment.CENTER),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.padding.symmetric(horizontal=20, vertical=10),
                ),
                
                ft.Divider(height=1, color=ft.colors.OUTLINE_VARIANT, opacity=0.5),

                # Routing Section
                self._build_section_header("Routing Bypass", ft.icons.ROUTE),
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text("Direct Country", size=16, weight=ft.FontWeight.W_500),
                            ft.Text("Traffic to this country will bypass proxy", size=12, color=ft.colors.ON_SURFACE_VARIANT),
                        ], expand=True),
                        self._country_dropdown
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.padding.symmetric(horizontal=20, vertical=10),
                ),

                ft.Divider(height=1, color=ft.colors.OUTLINE_VARIANT, opacity=0.5),

                # DNS Section
                self._build_section_header("DNS Configuration", ft.icons.DNS),
                ft.Container(
                    content=ft.Column([
                        ft.Text("Custom DNS Servers", size=16, weight=ft.FontWeight.W_500),
                        ft.Container(height=5),
                        ft.Row([
                            self._dns_field,
                            ft.IconButton(
                                icon=ft.icons.SAVE_OUTLINED,
                                icon_color=ft.colors.PRIMARY,
                                tooltip="Save DNS",
                                on_click=self._save_dns
                            )
                        ])
                    ]),
                    padding=ft.padding.symmetric(horizontal=20, vertical=10),
                ),

                ft.Divider(height=1, color=ft.colors.OUTLINE_VARIANT, opacity=0.5),

                # Proxy Settings Section
                self._build_section_header("Proxy Configuration", ft.icons.SETTINGS_ETHERNET),
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text("SOCKS Port", size=16, weight=ft.FontWeight.W_500),
                            ft.Text("Local listening port for proxy mode", size=12, color=ft.colors.ON_SURFACE_VARIANT),
                        ], expand=True),
                        ft.Row([
                            self._port_field,
                            ft.IconButton(
                                icon=ft.icons.SAVE_OUTLINED,
                                icon_color=ft.colors.PRIMARY,
                                tooltip="Save Port",
                                on_click=self._save_port
                            )
                        ])
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.padding.symmetric(horizontal=20, vertical=10),
                ),

                ft.Divider(height=1, color=ft.colors.OUTLINE_VARIANT, opacity=0.5),
                
                # Updates Section
                self._build_section_header("Updates", ft.icons.SYSTEM_UPDATE),
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            self._build_update_button("Xray Core", "xray"),
                            ft.Container(width=10),
                            self._build_update_button("Tun2Proxy", "tun2proxy"),
                        ]),
                        ft.Container(height=10),
                        self._build_update_button("Geo Files (Iran Rules)", "geo"),
                    ]),
                    padding=ft.padding.symmetric(horizontal=20, vertical=10),
                ),
                
                ft.Divider(height=1, color=ft.colors.OUTLINE_VARIANT, opacity=0.5),

                # About Section
                self._build_section_header("About", ft.icons.INFO_OUTLINE),
                ft.Container(
                    content=ft.Column([
                        ft.Text("XenRay Client", size=16, weight=ft.FontWeight.BOLD),
                        ft.Text("v1.0.0", size=12, color=ft.colors.ON_SURFACE_VARIANT),
                        ft.Container(height=5),
                        ft.Text("A modern, lightweight Xray client designed for performance and ease of use.", size=12, color=ft.colors.ON_SURFACE_VARIANT),
                        ft.Container(height=10),
                        ft.Text("Developed by Xenups", size=12, color=ft.colors.PRIMARY, weight=ft.FontWeight.BOLD),
                    ]),
                    padding=ft.padding.symmetric(horizontal=20, vertical=10),
                ),
            ],
            bgcolor=ft.colors.SURFACE,
            surface_tint_color=ft.colors.SURFACE_TINT,
        )
    
    def _build_section_header(self, title, icon):
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=18, color=ft.colors.PRIMARY),
                ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=ft.colors.PRIMARY),
            ], spacing=10),
            padding=ft.padding.only(left=20, top=15, bottom=5),
        )

    def _build_update_button(self, label, component):
        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.icons.DOWNLOAD_ROUNDED, size=16, color=ft.colors.ON_PRIMARY_CONTAINER),
                ft.Text(label, size=12, color=ft.colors.ON_PRIMARY_CONTAINER, weight=ft.FontWeight.W_500),
            ], alignment=ft.MainAxisAlignment.CENTER),
            bgcolor=ft.colors.PRIMARY_CONTAINER,
            padding=10,
            border_radius=8,
            on_click=lambda e: self._on_installer_run(component),
            ink=True,
            expand=True,
        )

    def _handle_mode_change(self, e):
        is_proxy = self._mode_switch.value
        
        # If switching to VPN (value=False), check admin
        if not is_proxy:
            if not ProcessUtils.is_admin():
                # Revert switch visually
                self._mode_switch.value = True
                self._mode_switch.update()
                # Trigger admin request in main window
                self._on_mode_changed(ConnectionMode.VPN) 
                return

        new_mode = ConnectionMode.PROXY if is_proxy else ConnectionMode.VPN
        self._on_mode_changed(new_mode)

    def _save_port(self, e):
        try:
            port = int(self._port_field.value)
            if 1024 <= port <= 65535:
                self._config_manager.set_proxy_port(port)
                self._port_field.error_text = ""
                if self._port_field.page:
                    self._port_field.page.show_snack_bar(
                        ft.SnackBar(content=ft.Text(f"Port set to {port}"))
                    )
            else:
                self._port_field.error_text = "1024-65535"
        except ValueError:
            self._port_field.error_text = "Invalid"
        
        self._port_field.update()

    def _save_country(self, e):
        import os
        from src.core.constants import ASSETS_DIR
        
        val = self._country_dropdown.value
        if val == "none":
            val = None
        else:
            # Check for geo files
            geoip_path = os.path.join(ASSETS_DIR, "geoip.dat")
            geosite_path = os.path.join(ASSETS_DIR, "geosite.dat")
            
            if not os.path.exists(geoip_path) or not os.path.exists(geosite_path):
                if self._country_dropdown.page:
                    self._country_dropdown.page.show_snack_bar(
                        ft.SnackBar(
                            content=ft.Text("Geo files missing! Please update via 'Updates' section."),
                            action="Update",
                            on_action=lambda e: self._on_installer_run("geo")
                        )
                    )
        
        self._config_manager.set_routing_country(val)
        if self._country_dropdown.page:
            self._country_dropdown.page.show_snack_bar(ft.SnackBar(content=ft.Text("Routing updated")))

    def _save_dns(self, e):
        val = self._dns_field.value
        self._config_manager.set_custom_dns(val)
        if self._dns_field.page:
            self._dns_field.page.show_snack_bar(ft.SnackBar(content=ft.Text("DNS updated")))
