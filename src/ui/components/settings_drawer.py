"""Settings drawer component with i18n support."""
from __future__ import annotations

import os
import threading
import time

import flet as ft
from loguru import logger

from src.core.app_context import AppContext
from src.core.constants import APP_VERSION
from src.core.i18n import set_language as set_app_language
from src.core.i18n import t
from src.core.types import ConnectionMode
from src.services import task_scheduler
from src.services.app_update_service import AppUpdateService
from src.services.singbox_service import SingboxService
from src.services.xray_installer import XrayInstallerService
from src.ui.components.settings_sections import (
    AutoReconnectToggleRow,
    CountryDropdownRow,
    LanguageDropdownRow,
    ModeSelectionRow,
    PortInputRow,
    SettingsListTile,
    SettingsSection,
    StartupToggleRow,
)
from src.utils.process_utils import ProcessUtils


class SettingsDrawer(ft.NavigationDrawer):
    """Settings drawer component."""

    def __init__(
        self,
        app_context: AppContext,
        on_installer_run,
        on_mode_changed,
        get_current_mode,
        navigate_to,
        navigate_back,
    ):
        self._app_context = app_context
        self._on_installer_run_external = on_installer_run
        self._on_mode_changed = on_mode_changed
        self._get_current_mode = get_current_mode
        self._navigate_to = navigate_to
        self._navigate_back = navigate_back

        # Mode state
        current_mode = self._get_current_mode()
        is_proxy = current_mode == ConnectionMode.PROXY

        # Components
        self._mode_selection_row = ModeSelectionRow(current_mode.value, self._handle_mode_change)
        self._port_row = PortInputRow(
            self._app_context.settings.get_proxy_port(),
            self._save_port,
        )
        self._country_row = CountryDropdownRow(
            self._app_context.settings.get_routing_country(),
            self._save_country,
        )
        self._language_row = LanguageDropdownRow(
            self._app_context.settings.get_language(),
            self._save_language,
        )

        # Startup toggle (self-contained component)
        self._startup_row = StartupToggleRow(
            app_context=self._app_context,
            is_registered=task_scheduler.is_task_registered(),
            is_supported=task_scheduler.is_supported(),
            on_register=task_scheduler.register_task,
            on_unregister=task_scheduler.unregister_task,
            toast_callback=self._show_toast,
        )

        # Auto-reconnect toggle (self-contained component)
        self._auto_reconnect_row = AutoReconnectToggleRow(
            app_context=self._app_context,
            toast_callback=self._show_toast,
        )

        # Build UI
        # Glass container wrapping all content
        glass_content = ft.Container(
            content=ft.Column(
                [
                    # Top Bar with Back Button
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.IconButton(
                                    ft.Icons.ARROW_BACK,
                                    on_click=self._close_drawer,
                                ),
                                ft.Text(
                                    t("settings.title"),
                                    size=20,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ],
                        ),
                        padding=20,
                    ),
                    ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.2),
                    # Content
                    ft.Container(
                        content=ft.Column(
                            [
                                # Connection Section
                                SettingsSection(
                                    t("settings.connection"),
                                    [
                                        self._mode_selection_row,
                                        self._port_row,
                                        self._country_row,
                                    ],
                                ),
                                ft.Divider(
                                    height=1,
                                    color=ft.Colors.OUTLINE_VARIANT,
                                    opacity=0.2,
                                ),
                                ft.Container(height=10),
                                # App Settings
                                SettingsSection(
                                    t("settings.application"),
                                    [
                                        self._startup_row,
                                        self._auto_reconnect_row,
                                        SettingsListTile(
                                            ft.Icons.ROUTE,
                                            t("settings.routing_rules"),
                                            t("settings.routing_description"),
                                            on_click=self._open_routing_manager,
                                        ),
                                        SettingsListTile(
                                            ft.Icons.DNS,
                                            t("settings.dns_manager"),
                                            t("settings.dns_description"),
                                            on_click=self._open_dns_manager,
                                        ),
                                        SettingsListTile(
                                            ft.Icons.RESTART_ALT,
                                            t("settings.reset_close_choice"),
                                            t("settings.reset_close_choice_desc"),
                                            on_click=self._reset_close_preference,
                                        ),
                                    ],
                                ),
                                ft.Divider(
                                    height=1,
                                    color=ft.Colors.OUTLINE_VARIANT,
                                    opacity=0.2,
                                ),
                                ft.Container(height=10),
                                # System Section
                                SettingsSection(
                                    t("settings.system"),
                                    [
                                        SettingsListTile(
                                            ft.Icons.UPGRADE,
                                            t("settings.check_app_updates"),
                                            t("settings.app_update_description"),
                                            on_click=self._check_app_updates,
                                        ),
                                        SettingsListTile(
                                            ft.Icons.SYSTEM_UPDATE_ALT,
                                            t("settings.check_updates"),
                                            t("settings.update_xray"),
                                            on_click=lambda e: self._on_installer_run("xray"),
                                        ),
                                        SettingsListTile(
                                            ft.Icons.INFO_OUTLINE,
                                            t("settings.about"),
                                            f"v{APP_VERSION} by Xenups",
                                            show_chevron=False,
                                        ),
                                        self._language_row,
                                    ],
                                ),
                            ],
                            scroll=ft.ScrollMode.HIDDEN,
                        ),
                        expand=True,
                    ),
                    # Version Footer
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(
                                    f"Xray: v{XrayInstallerService.get_local_version() or 'ND'}",
                                    size=11,
                                    color=ft.Colors.OUTLINE,
                                ),
                                ft.Container(
                                    width=1,
                                    height=10,
                                    bgcolor=ft.Colors.OUTLINE_VARIANT,
                                ),
                                ft.Text(
                                    f"Sing-box: v{SingboxService().get_version() or 'ND'}",
                                    size=11,
                                    color=ft.Colors.OUTLINE,
                                ),
                            ],
                            spacing=10,
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        alignment=ft.alignment.center,
                        padding=20,
                    ),
                ],
                spacing=0,
            ),
            bgcolor=ft.Colors.with_opacity(0.7, "#0f172a"),
            blur=ft.Blur(20, 20, ft.BlurTileMode.MIRROR),
            expand=True,
        )

        # Wrap in container to control width
        drawer_container = ft.Container(
            content=glass_content,
            width=320,
        )

        super().__init__(
            controls=[drawer_container],
            bgcolor=ft.Colors.TRANSPARENT,
            surface_tint_color=ft.Colors.TRANSPARENT,
            shadow_color=ft.Colors.TRANSPARENT,
        )

    def _close_drawer(self, e=None):
        """Close this settings drawer."""
        self.open = False
        if self.page:
            self.page.close(self)

    def _handle_mode_change(self, val):
        """Handle Connection mode change."""
        new_mode_str = val
        
        if new_mode_str in ["vpn", "tor"] and not ProcessUtils.is_admin():
            self._mode_selection_row.value = "proxy"
            self._mode_selection_row.update()
            self._show_admin_restart_dialog(new_mode_str)
            return

        new_mode = ConnectionMode(new_mode_str)
        self._on_mode_changed(new_mode)

    def _show_admin_restart_dialog(self, target_mode_str: str):
        """Show dialog to restart as admin for VPN/Tor mode."""
        page = self.page
        if not page:
            return

        def close_dlg(e):
            page.close(dlg)

        def confirm_restart(e):
            page.close(dlg)
            self._app_context.settings.set_connection_mode(target_mode_str)
            ProcessUtils.restart_as_admin()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("admin.title")),
            content=ft.Text(t("admin.message")),
            actions=[
                ft.TextButton(t("admin.cancel"), on_click=close_dlg),
                ft.TextButton(t("admin.restart"), on_click=confirm_restart),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    def _show_toast(self, message: str, message_type: str = "info"):
        """Show a toast notification."""
        if hasattr(self.page, "_toast_manager"):
            self.page._toast_manager.show(message, message_type)
        elif self.page:
            # Log if toast manager is missing
            logger.warning("Toast manager not available, message not shown")

    def _save_port(self, value: str):
        """Save the SOCKS port setting."""
        page = self.page
        if not page:
            return

        try:
            port = int(value)
            if 1024 <= port <= 65535:
                self._app_context.settings.set_proxy_port(port)
                self._port_row.set_border_color(ft.Colors.GREEN_400)
                self._show_toast(t("settings.port_saved", port=port), "success")
            else:
                self._port_row.set_border_color(ft.Colors.RED_400)
                self._show_toast(t("settings.port_invalid_range"), "error")
        except ValueError:
            self._port_row.set_border_color(ft.Colors.RED_400)
            self._show_toast(t("settings.port_must_be_number"), "error")

        page.update()

    def _save_country(self, e):
        """Save the direct country setting."""
        page = self.page
        if not page:
            return

        val = self._country_row.value
        self._app_context.settings.set_routing_country(val)
        self._show_toast(t("settings.country_saved", val=val), "success")
        page.update()

    def _save_language(self, e):
        """Save the language setting and update i18n."""
        page = self.page
        if not page:
            return

        lang = self._language_row.value
        self._app_context.settings.set_language(lang)
        set_app_language(lang)

        # Notify user - app needs restart for full effect
        msg = t("settings.language_restart_msg")
        self._show_toast(msg, "success")
        page.update()

    def _reset_close_preference(self, e):
        """Reset the 'Remember Choice' for close dialog."""
        page = self.page
        if not page:
            return

        self._app_context.settings.set_remember_close_choice(False)
        self._show_toast(t("settings.reset_close_success"), "success")
        page.update()

    def _on_installer_run(self, component: str):
        """Handle update/install request."""
        page = self.page
        if not page:
            return

        if component == "xray":
            self._show_toast(t("update.checking"), "info")

            try:
                available, current, latest = XrayInstallerService.check_for_updates()

                # If up to date, show message and return
                if not available and current:
                    self._show_toast(t("update.up_to_date", version=current), "info")
                    page.update()
                    return

                # If update is available, show update dialog
                if available and latest:
                    self._show_update_dialog(page, current, latest)
                else:
                    # Failed to check or no update info
                    self._show_toast(t("update.check_failed"), "error")
                    page.update()

            except Exception as e:
                logger.error(f"Update check failed: {e}")
                self._show_toast(t("update.check_failed"), "error")
                page.update()

    def _show_update_dialog(self, page, current: str, latest: str):
        """Show update confirmation dialog."""
        msg = t("update.available", current=current, latest=latest) if current else t("update.install", version=latest)

        def close_dlg(e):
            page.close(dlg)

        def start_update(e):
            page.close(dlg)
            self._run_update_process(page)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("update.title")),
            content=ft.Text(msg),
            actions=[
                ft.TextButton(t("add_dialog.cancel"), on_click=close_dlg),
                ft.TextButton(t("add_dialog.add"), on_click=start_update),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    def _run_update_process(self, page):
        """Run the update process with progress dialog."""
        progress_ring = ft.ProgressRing(width=16, height=16, stroke_width=2)
        status_text = ft.Text(t("update.starting"), size=12)

        progress_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("update.updating")),
            content=ft.Column(
                [
                    ft.Row(
                        [progress_ring, status_text],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
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
                self._show_toast(t("update.success"), "success")
            else:
                self._show_toast(t("update.failed"), "error")
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
        routing_page = RoutingPage(self._app_context, on_back=self._on_subpage_back)
        self._navigate_to(routing_page)

    def _open_dns_manager(self, e):
        """Open the DNS settings page."""
        from src.ui.pages.dns_page import DNSPage

        self.open = False
        self.update()
        dns_page = DNSPage(self._app_context, on_back=self._on_subpage_back)
        self._navigate_to(dns_page)

    def _check_app_updates(self, e):
        """Check for app updates."""
        page = self.page
        if not page:
            return

        self._show_toast(t("app_update.checking"), "info")

        def check_task():
            try:
                (
                    available,
                    current,
                    latest,
                    download_url,
                ) = AppUpdateService.check_for_updates()

                if not available and current:
                    self._show_toast(t("app_update.up_to_date", version=current), "info")
                    page.update()
                    return

                if available and download_url:
                    self._show_app_update_dialog(page, current, latest, download_url)
                else:
                    self._show_toast(t("app_update.check_failed"), "error")
                    page.update()
            except Exception:
                self._show_toast(t("app_update.check_failed"), "error")
                page.update()

        threading.Thread(target=check_task, daemon=True).start()

    def _show_app_update_dialog(self, page, current: str, latest: str, download_url: str):
        """Show app update confirmation dialog."""
        msg = (
            t("app_update.available", current=current, latest=latest)
            if current
            else t("app_update.install", version=latest)
        )

        def close_dlg(e):
            page.close(dlg)

        def start_update(e):
            page.close(dlg)
            self._run_app_update_process(page, download_url)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("app_update.title")),
            content=ft.Column(
                [
                    ft.Text(msg),
                    ft.Text(
                        t("app_update.message"),
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                tight=True,
                spacing=10,
            ),
            actions=[
                ft.TextButton(t("app_update.cancel"), on_click=close_dlg),
                ft.TextButton(t("app_update.confirm"), on_click=start_update),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    def _run_app_update_process(self, page, download_url: str):
        """Run the app update process with progress dialog."""
        progress_ring = ft.ProgressRing(width=16, height=16, stroke_width=2)
        status_text = ft.Text(t("app_update.downloading", progress=0), size=12)

        progress_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("app_update.title")),
            content=ft.Column(
                [
                    ft.Row(
                        [progress_ring, status_text],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            actions=[],
        )
        page.open(progress_dlg)
        page.update()

        def update_task():
            def on_progress(progress: int):
                status_text.value = t("app_update.downloading", progress=progress)
                status_text.update()

            # Download update
            zip_path = AppUpdateService.download_update(download_url, on_progress)

            if not zip_path:
                page.close(progress_dlg)
                self._show_toast(t("app_update.download_failed"), "error")
                return

            # Update status
            status_text.value = t("app_update.extracting")
            status_text.update()

            # Apply update (launches updater and exits)
            success = AppUpdateService.apply_update(zip_path)

            if success:
                # The updater will handle the rest, signal app to close
                status_text.value = t("app_update.restarting")
                status_text.update()
                time.sleep(1)

                # Trigger app exit
                ProcessUtils.kill_process_tree()
                os._exit(0)
            else:
                page.close(progress_dlg)
                self._show_toast(t("app_update.extract_failed"), "error")
                page.update()

        threading.Thread(target=update_task, daemon=True).start()
