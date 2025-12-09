"""Settings drawer component using reusable section components."""
from __future__ import annotations
import threading
import flet as ft

from src.core.config_manager import ConfigManager
from src.core.types import ConnectionMode
from src.utils.process_utils import ProcessUtils
from src.services.xray_installer import XrayInstallerService
from src.services.singbox_service import SingboxService
from src.ui.components.settings_sections import (
    SettingsSection,
    SettingsListTile,
    ModeSwitchRow,
    PortInputRow,
    CountryDropdownRow,
)


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
        self._on_installer_run_external = on_installer_run
        self._on_mode_changed = on_mode_changed
        self._get_current_mode = get_current_mode
        self._navigate_to = navigate_to
        self._navigate_back = navigate_back

        # Mode state
        current_mode = self._get_current_mode()
        is_proxy = current_mode == ConnectionMode.PROXY

        # Components
        self._mode_switch_row = ModeSwitchRow(is_proxy, self._handle_mode_change)
        self._port_row = PortInputRow(
            self._config_manager.get_proxy_port(),
            self._save_port,
        )
        self._country_row = CountryDropdownRow(
            self._config_manager.get_routing_country(),
            self._save_country,
        )

        # Build UI
        super().__init__(
            controls=[
                # Header
                ft.Container(
                    content=ft.Column([
                        ft.Text("Settings", size=28, weight=ft.FontWeight.BOLD),
                        ft.Text("Configure your connection", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    ], spacing=2),
                    padding=ft.padding.only(left=20, top=20, bottom=20),
                ),
                # General Section
                SettingsSection("General", [self._mode_switch_row]),
                ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.2),
                ft.Container(height=10),
                # Network Section
                SettingsSection("Network", [
                    self._country_row,
                    self._port_row,
                ]),
                ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.2),
                ft.Container(height=10),
                # Advanced Section
                SettingsSection("Advanced", [
                    SettingsListTile(
                        ft.Icons.DIRECTIONS,
                        "Routing Rules",
                        "Manage direct, proxy, and block lists",
                        on_click=self._open_routing_manager,
                    ),
                    SettingsListTile(
                        ft.Icons.DNS,
                        "DNS Settings",
                        "Configure upstream DNS servers",
                        on_click=self._open_dns_manager,
                    ),
                ]),
                ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.2),
                ft.Container(height=10),
                # System Section
                SettingsSection("System", [
                    SettingsListTile(
                        ft.Icons.SYSTEM_UPDATE_ALT,
                        "Check for Updates",
                        "Update Xray Core",
                        on_click=lambda e: self._on_installer_run("xray"),
                    ),
                    SettingsListTile(
                        ft.Icons.INFO_OUTLINE,
                        "About XenRay",
                        "v1.0.0 by Xenups",
                        show_chevron=False,
                    ),
                ]),
                # Version Footer
                ft.Container(
                    content=ft.Row([
                        ft.Text(
                            f"Xray: v{XrayInstallerService.get_local_version() or 'ND'}",
                            size=11, color=ft.Colors.OUTLINE,
                        ),
                        ft.Container(width=1, height=10, bgcolor=ft.Colors.OUTLINE_VARIANT),
                        ft.Text(
                            f"Sing-box: v{SingboxService().get_version() or 'ND'}",
                            size=11, color=ft.Colors.OUTLINE,
                        ),
                    ], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                    alignment=ft.alignment.center,
                    padding=20,
                ),
            ],
            bgcolor=ft.Colors.SURFACE,
            surface_tint_color=ft.Colors.SURFACE_TINT,
        )

    def _handle_mode_change(self, e):
        """Handle VPN/Proxy mode switch."""
        is_proxy = self._mode_switch_row.value

        if not is_proxy and not ProcessUtils.is_admin():
            # VPN mode requires admin
            self._mode_switch_row.value = True
            self._mode_switch_row.update()
            self._show_admin_restart_dialog()
            return

        new_mode = ConnectionMode.PROXY if is_proxy else ConnectionMode.VPN
        self._on_mode_changed(new_mode)

    def _show_admin_restart_dialog(self):
        """Show dialog to restart as admin for VPN mode."""
        page = self.page
        if not page:
            return

        def close_dlg(e):
            page.close(dlg)

        def confirm_restart(e):
            page.close(dlg)
            self._config_manager.set_connection_mode(ConnectionMode.VPN.value)
            ProcessUtils.restart_as_admin()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Admin Rights Required"),
            content=ft.Text(
                "VPN mode requires Administrator privileges.\n\n"
                "Do you want to restart the application as Admin?"
            ),
            actions=[
                ft.TextButton("Cancel", on_click=close_dlg),
                ft.TextButton("Restart", on_click=confirm_restart),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    def _save_port(self, value: str):
        """Save the SOCKS port setting."""
        page = self.page
        if not page:
            return

        try:
            port = int(value)
            if 1024 <= port <= 65535:
                self._config_manager.set_proxy_port(port)
                self._port_row.set_border_color(ft.Colors.GREEN_400)
                page.open(ft.SnackBar(content=ft.Text(f"SOCKS Port saved: {port} 💾")))
            else:
                self._port_row.set_border_color(ft.Colors.RED_400)
                page.open(ft.SnackBar(content=ft.Text("Invalid Port Range (1024-65535)"), bgcolor=ft.Colors.RED_700))
        except ValueError:
            self._port_row.set_border_color(ft.Colors.RED_400)
            page.open(ft.SnackBar(content=ft.Text("Port must be a number"), bgcolor=ft.Colors.RED_700))

        page.update()

    def _save_country(self, e):
        """Save the direct country setting."""
        page = self.page
        if not page:
            return

        val = self._country_row.value
        self._config_manager.set_routing_country(val)
        page.open(ft.SnackBar(content=ft.Text(f"Direct Country saved: {val} 🌐")))
        page.update()

    def _on_installer_run(self, component: str):
        """Handle update/install request."""
        page = self.page
        if not page:
            return

        if component == "xray":
            page.open(ft.SnackBar(content=ft.Text("Checking for updates... 📡")))
            page.update()

            try:
                available, current, latest = XrayInstallerService.check_for_updates()
                if not available and current:
                    page.open(ft.SnackBar(content=ft.Text(f"You are up to date! (v{current}) ✅")))
                    page.update()
                    return
            except Exception:
                pass

            self._show_update_dialog(page, current, latest)

    def _show_update_dialog(self, page, current: str, latest: str):
        """Show update confirmation dialog."""
        msg = f"Update available: v{current} -> v{latest}" if current else f"Install Xray Core v{latest}?"

        def close_dlg(e):
            page.close(dlg)

        def start_update(e):
            page.close(dlg)
            self._run_update_process(page)

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

    def _run_update_process(self, page):
        """Run the update process with progress dialog."""
        progress_ring = ft.ProgressRing(width=16, height=16, stroke_width=2)
        status_text = ft.Text("Starting...", size=12)

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
                ProcessUtils.kill_process_by_name("xray.exe")
                ProcessUtils.kill_process_by_name("sing-box.exe")

            success = XrayInstallerService.install(
                progress_callback=on_progress,
                stop_service_callback=stop_service,
            )

            page.close(progress_dlg)
            if success:
                page.open(ft.SnackBar(content=ft.Text("Xray Updated Successfully! 🎉"), bgcolor=ft.Colors.GREEN_700))
            else:
                page.open(ft.SnackBar(content=ft.Text("Update Failed! ❌"), bgcolor=ft.Colors.RED_700))
            page.update()

        threading.Thread(target=update_task, daemon=True).start()

    def _on_subpage_back(self, e):
        """Handle navigation back from subpage."""
        self._navigate_back()
        self.open = True
        self.page.update()

    def _open_routing_manager(self, e):
        """Open the routing rules page."""
        from src.ui.pages.routing_page import RoutingPage
        self.open = False
        self.update()
        routing_page = RoutingPage(self._config_manager, on_back=self._on_subpage_back)
        self._navigate_to(routing_page)

    def _open_dns_manager(self, e):
        """Open the DNS settings page."""
        from src.ui.pages.dns_page import DNSPage
        self.open = False
        self.update()
        dns_page = DNSPage(self._config_manager, on_back=self._on_subpage_back)
        self._navigate_to(dns_page)
