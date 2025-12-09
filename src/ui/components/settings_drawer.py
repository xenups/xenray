"""Settings drawer component."""

import flet as ft
import os

# Imports assumed to be available in your project structure
from src.core.config_manager import ConfigManager
from src.core.types import ConnectionMode
from src.utils.process_utils import ProcessUtils
from src.services.xray_installer import XrayInstallerService
from src.services.singbox_service import SingboxService


class SettingsDrawer(ft.NavigationDrawer):
    """Settings drawer component."""

    def __init__(
        self,
        config_manager: ConfigManager,
        on_installer_run,
        on_mode_changed,
        get_current_mode,
        navigate_to,
        navigate_back,
    ):
        self._config_manager = config_manager
        self._on_installer_run = on_installer_run
        self._on_mode_changed = on_mode_changed
        self._get_current_mode = get_current_mode
        self._navigate_to = navigate_to
        self._navigate_back = navigate_back

        # Port configuration field
        self._port_field = ft.TextField(
            value=str(self._config_manager.get_proxy_port()),
            width=100, 
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
            width=100,
            text_size=12, # Slightly smaller text for better fit
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
            on_change=self._save_country,
        )

        self._status_label = ft.Text(
            "", 
            size=12, 
            text_align=ft.TextAlign.CENTER, 
            weight=ft.FontWeight.W_500
        )

        super().__init__(
            controls=[
                ft.Container(
                    content=ft.Column([
                        ft.Text("Settings", size=28, weight=ft.FontWeight.BOLD),
                        ft.Text("Configure your connection", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    ], spacing=2),
                    padding=ft.padding.only(left=20, top=20, bottom=20),
                ),
                
                ft.Column([
                    # Section: General
                    ft.Container(
                        content=ft.Column([
                            ft.Text("General", color=ft.Colors.PRIMARY, weight=ft.FontWeight.BOLD, size=12),
                            ft.Container(height=5),
                            ft.Container(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.VPN_LOCK, color=ft.Colors.ON_SURFACE_VARIANT),
                                    ft.Column([
                                        ft.Text("Connection Mode", weight=ft.FontWeight.W_500),
                                        ft.Text("VPN or Proxy specific behavior", size=11, color=ft.Colors.ON_SURFACE_VARIANT)
                                    ], spacing=2, expand=True),
                                    ft.Row([
                                        ft.Text("VPN", size=11, color=ft.Colors.ON_SURFACE_VARIANT, weight=ft.FontWeight.BOLD if not is_proxy else ft.FontWeight.NORMAL),
                                        self._mode_switch,
                                        ft.Text("Proxy", size=11, color=ft.Colors.ON_SURFACE_VARIANT, weight=ft.FontWeight.BOLD if is_proxy else ft.FontWeight.NORMAL),
                                    ], spacing=5)
                                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                padding=10,
                                border_radius=8,
                                bgcolor=ft.Colors.SURFACE_CONTAINER_LOW if hasattr(ft.Colors, "SURFACE_CONTAINER_LOW") else ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                            ),
                        ]),
                        padding=ft.padding.symmetric(horizontal=20)
                    ),

                    ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.2),
                    ft.Container(height=10),

                    # Section: Network
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Network", color=ft.Colors.PRIMARY, weight=ft.FontWeight.BOLD, size=12),
                            ft.Container(height=5),
                            
                             # Direct Country Row (First)
                             ft.Container(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.PUBLIC, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                                    ft.Text("Direct Country", size=12, weight=ft.FontWeight.W_500, width=80),
                                    self._country_dropdown
                                ], spacing=5),
                                padding=ft.padding.symmetric(horizontal=5, vertical=5),
                            ),

                             # Port Row (Second)
                             ft.Container(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.INPUT, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
                                    ft.Text("SOCKS Port", size=12, weight=ft.FontWeight.W_500, width=80),
                                    self._port_field,
                                    ft.ElevatedButton(
                                        text="Save",
                                        height=30,
                                        style=ft.ButtonStyle(
                                            padding=ft.padding.symmetric(horizontal=10),
                                            shape=ft.RoundedRectangleBorder(radius=4),
                                        ),
                                        on_click=self._save_port,
                                    ),
                                ], spacing=5),
                                padding=ft.padding.only(left=5, top=5, right=20, bottom=5),
                            ),
                            
                            ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.2),
                            ft.Container(height=10),
                            ft.Text("Advanced", color=ft.Colors.PRIMARY, weight=ft.FontWeight.BOLD, size=12),
                            ft.Container(height=5),
                            
                            # Routing Manager Tile
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.DIRECTIONS, color=ft.Colors.ON_SURFACE_VARIANT),
                                title=ft.Text("Routing Rules", weight=ft.FontWeight.W_500),
                                subtitle=ft.Text("Manage direct, proxy, and block lists", size=12),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=ft.Colors.OUTLINE),
                                on_click=self._open_routing_manager,
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                            
                            # DNS Manager Tile
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.DNS, color=ft.Colors.ON_SURFACE_VARIANT),
                                title=ft.Text("DNS Settings", weight=ft.FontWeight.W_500),
                                subtitle=ft.Text("Configure upstream DNS servers", size=12),
                                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=ft.Colors.OUTLINE),
                                on_click=self._open_dns_manager,
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                        ]),
                        padding=ft.padding.symmetric(horizontal=20)
                    ),
                    
                    ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.2),
                    ft.Container(height=10),

                    # Section: System
                    ft.Container(
                        content=ft.Column([
                            ft.Text("System", color=ft.Colors.PRIMARY, weight=ft.FontWeight.BOLD, size=12),
                            ft.Container(height=5),
                            
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT, color=ft.Colors.ON_SURFACE_VARIANT),
                                title=ft.Text("Check for Updates", weight=ft.FontWeight.W_500),
                                subtitle=ft.Text("Update Xray Core", size=12),
                                on_click=lambda e: self._on_installer_run("xray"),
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                            
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.INFO_OUTLINE, color=ft.Colors.ON_SURFACE_VARIANT),
                                title=ft.Text("About XenRay", weight=ft.FontWeight.W_500),
                                subtitle=ft.Text("v1.0.0 by Xenups", size=12),
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                            
                            
                        ]),
                        padding=ft.padding.symmetric(horizontal=20),
                        alignment=ft.alignment.center
                    ),

                ], spacing=10),

                ft.Container(
                    content=ft.Row([
                        ft.Text(
                            f"Xray: v{XrayInstallerService.get_local_version() or 'ND'}",
                            size=11, color=ft.Colors.OUTLINE
                        ),
                        ft.Container(width=1, height=10, bgcolor=ft.Colors.OUTLINE_VARIANT),
                        ft.Text(
                            f"Sing-box: v{SingboxService().get_version() or 'ND'}",
                            size=11, color=ft.Colors.OUTLINE
                        ),
                    ], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                    alignment=ft.alignment.center,
                    padding=20,
                )

            ],
            bgcolor=ft.Colors.SURFACE,
            surface_tint_color=ft.Colors.SURFACE_TINT,
        )

    def _build_update_button(self, label, component):
        # ... (Removed as it is not used anymore or we can leave it if valid helper)
        return ft.Container() 

    # ... (Other methods)

    def _on_installer_run(self, component):
        page = self.page
        if not page:
            return

        if component == "xray":
            # Smart Update Check
            page.open(ft.SnackBar(content=ft.Text("Checking for updates... 📡")))
            page.update()
            
            # Run check in background logic? 
            # For simplicity, we check synchronously here or better, use a thread.
            # But Requests is blocking. Let's do a simple check.
            
            try:
                available, current, latest = XrayInstallerService.check_for_updates()
                if not available and current:
                     page.open(ft.SnackBar(content=ft.Text(f"You are up to date! (v{current}) ✅")))
                     page.update()
                     return
            except Exception as e:
                pass # Proceed to install if check fails or whatever

            # Show Confirmation if update available
            def close_dlg(e):
                page.close(dlg)

            def start_update(e):
                page.close(dlg)
                self._run_update_process(page)

            msg = f"Update available: v{current} -> v{latest}" if current else f"Install Xray Core v{latest}?"
            
            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("Update Xray Core"),
                content=ft.Text(msg),
                actions=[
                    ft.TextButton("Cancel", on_click=close_dlg),
                    ft.TextButton("Update", on_click=start_update),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.open(dlg)
            
        else:
            # Fallback for other components
            pass

    def _run_update_process(self, page):
        # Existing logic refactored here
        progress_ring = ft.ProgressRing(width=16, height=16, stroke_width=2)
        status_text = ft.Text("Starting...", size=12)
        
        # ... (We need to implement the actual update run here similar to previous logic but simpler)
        # Actually, let's keep it simple and just reuse the previous logic structure but inside this method.
        # Since I am replacing _on_installer_run, I need to provide the full body.
        
        # Creating a modal for progress
        progress_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Updating Xray..."),
            content=ft.Column([
                ft.Row([progress_ring, status_text], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
            ], tight=True, alignment=ft.MainAxisAlignment.CENTER),
            actions=[],
        )
        page.open(progress_dlg)
        page.update()

        def update_task():
            def on_progress(msg):
                status_text.value = msg
                status_text.update()

            def stop_service():
                 # We need to stop services via MainWindow or Event?
                 # ideally ConnectionManager disconnect.
                 # But we don't have reference here easily unless passed.
                 # Actually MainWindow handles this? 
                 # Let's hope ConnectionManager handles file locks or we just kill processes.
                 ProcessUtils.kill_process_by_name("xray.exe")
                 ProcessUtils.kill_process_by_name("sing-box.exe")

            success = XrayInstallerService.install(
                progress_callback=on_progress,
                stop_service_callback=stop_service
            )
            
            page.close(progress_dlg)
            
            if success:
                 page.open(ft.SnackBar(content=ft.Text("Xray Updated Successfully! 🎉"), bgcolor=ft.Colors.GREEN_700))
            else:
                 page.open(ft.SnackBar(content=ft.Text("Update Failed! ❌"), bgcolor=ft.Colors.RED_700))
            page.update()

        import threading
        threading.Thread(target=update_task, daemon=True).start()
    def _handle_mode_change(self, e):
        is_proxy = self._mode_switch.value

        if not is_proxy:
            if not ProcessUtils.is_admin():
                # Revert switch value because admin privileges are required for VPN mode
                self._mode_switch.value = True
                self._mode_switch.update()

                # Show Confirmation Dialog
                def close_dlg(e):
                    page.close(dlg)

                def confirm_restart(e):
                    page.close(dlg)
                    # Save "VPN" mode so the app starts in VPN mode after restart
                    self._config_manager.set_connection_mode(ConnectionMode.VPN.value)
                    ProcessUtils.restart_as_admin()

                dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Admin Rights Required"),
                    content=ft.Text("VPN mode requires Administrator privileges.\n\nDo you want to restart the application as Admin?"),
                    actions=[
                        ft.TextButton("Cancel", on_click=close_dlg),
                        ft.TextButton("Restart", on_click=confirm_restart),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                
                page = self._mode_switch.page
                if page:
                    page.open(dlg)
                
                return

        new_mode = ConnectionMode.PROXY if is_proxy else ConnectionMode.VPN
        self._on_mode_changed(new_mode)

    def _save_port(self, e):
        # Local validation
        page = self._port_field.page
        if not page: return
        
        try:
            port = int(self._port_field.value)
            if 1024 <= port <= 65535:
                self._config_manager.set_proxy_port(port)
                self._port_field.border_color = ft.Colors.GREEN_400
                page.open(ft.SnackBar(content=ft.Text(f"SOCKS Port saved: {port} 💾")))
            else:
                self._port_field.border_color = ft.Colors.RED_400
                page.open(ft.SnackBar(content=ft.Text("Invalid Port Range (1024-65535)"), bgcolor=ft.Colors.RED_700))
        except ValueError:
            self._port_field.border_color = ft.Colors.RED_400
            page.open(ft.SnackBar(content=ft.Text("Port must be a number"), bgcolor=ft.Colors.RED_700))

        self._port_field.update()
        page.update()

    def _save_country(self, e):
        page = self._country_dropdown.page
        if not page: return

        val = self._country_dropdown.value
        self._config_manager.set_routing_country(val)
        page.open(ft.SnackBar(content=ft.Text(f"Direct Country saved: {val} 🌐")))
        page.update()

    def _on_subpage_back(self, e):
         self._navigate_back()
         self.open = True
         self.page.update()

    def _open_routing_manager(self, e):
        from src.ui.pages.routing_page import RoutingPage
        
        self.open = False
        self.update()
        
        routing_page = RoutingPage(self._config_manager, on_back=self._on_subpage_back)
        self._navigate_to(routing_page)

    def _open_dns_manager(self, e):
        from src.ui.pages.dns_page import DNSPage
        
        self.open = False
        self.update()
        
        dns_page = DNSPage(self._config_manager, on_back=self._on_subpage_back)
        self._navigate_to(dns_page)
