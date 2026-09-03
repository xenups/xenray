"""Settings Handler - orchestrates settings drawer flows, update checks, dialogs, and navigation.

UI sections and components stay presentational; backend state mutation, service/IPC
calls, and orchestration live here (with simple persistence delegated to SettingsController).
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import flet as ft

from src.core.i18n import t
from src.core.types import ConnectionMode
from src.services.installer.app_update_service import AppUpdateService
from src.services.installer.rule_update_service import RuleUpdateService
from src.services.installer.xray_installer import XrayInstallerService
from src.utils.process_utils import ProcessUtils


class SettingsHandler:
    """Coordinates settings UI flows without leaking backend services into components."""

    def __init__(
        self,
        *,
        app_context,
        controller,
        show_toast: Callable[[str, str], None],
        get_page: Callable[[], Optional[ft.Page]],
        on_mode_changed: Callable[[ConnectionMode], None],
        navigate_to: Callable[[ft.Control], None],
        navigate_back: Callable,
        on_installer_run: Callable[[str], None],
    ) -> None:
        self._app_context = app_context
        self._controller = controller
        self._show_toast = show_toast
        self._get_page = get_page
        self._on_mode_changed = on_mode_changed
        self._navigate_to = navigate_to
        self._navigate_back = navigate_back
        self._on_installer_run = on_installer_run

    @property
    def controller(self):
        """Expose the backing SettingsController for direct persistence calls."""
        return self._controller

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _page(self) -> Optional[ft.Page]:
        try:
            return self._get_page()
        except Exception:
            return None

    def get_xray_version(self) -> str:
        """Read the installed Xray version for the footer text."""
        try:
            xray_ver = XrayInstallerService.get_local_version() or "ND"
        except Exception:
            xray_ver = "ND"
        return f"Xray: v{xray_ver}"

    # ------------------------------------------------------------------
    # Connection mode
    # ------------------------------------------------------------------
    def handle_mode_change(self, mode_row, e=None):
        """Handle VPN/Proxy mode switch, guarding VPN against non-admin usage."""
        is_proxy = bool(e.control.value) if (e and hasattr(e, "control") and e.control) else mode_row.value

        if not is_proxy and not ProcessUtils.is_admin():
            mode_row.value = True
            self._show_admin_restart_dialog()
            return

        self._on_mode_changed(ConnectionMode.PROXY if is_proxy else ConnectionMode.VPN)
        self._show_toast(
            t(
                "status.mode_selected",
                mode="Proxy" if is_proxy else "VPN",
                default=f"Mode: {'Proxy' if is_proxy else 'VPN'}",
            ),
            "success",
        )

    def _show_admin_restart_dialog(self):
        """Show dialog to restart as admin for VPN mode."""
        page = self._page()
        if not page:
            return

        def close_dlg(e):
            try:
                page.pop_dialog()
            except Exception:
                pass

        def confirm_restart(e):
            try:
                page.pop_dialog()
            except Exception:
                pass
            self._app_context.settings.set_connection_mode(ConnectionMode.VPN.value)
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
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Persistence saves (delegated to SettingsController)
    # ------------------------------------------------------------------
    def save_port(self, port_row, value: str):
        """Save the SOCKS port setting."""
        success, _ = self._controller.update_socks_port(value)
        port_row.set_border_color(ft.Colors.GREEN_400 if success else ft.Colors.RED_400)

    def save_http_port(self, http_row, value: str):
        """Save the HTTP proxy port setting."""
        success, _ = self._controller.update_http_port(value)
        http_row.set_border_color(ft.Colors.GREEN_400 if success else ft.Colors.RED_400)

    def save_country(self, country_row, val):
        """Save the direct country setting."""
        code = val if isinstance(val, str) else country_row.value
        self._controller.update_routing_country(code)

    def save_tun_engine(self, tun_row, e=None):
        """Save the TUN implementation setting."""
        self._controller.update_tun_engine(tun_row.value)

    def save_language(self, lang_row, e=None):
        """Save the language setting and notify the user a restart is needed."""
        page = self._page()

        lang = None
        if e is not None and hasattr(e, "control") and e.control is not None:
            lang = getattr(e.control, "value", None)
        if not lang:
            lang = lang_row.value
        if not lang:
            lang = getattr(e, "data", None)
        if not lang:
            return

        self._controller.update_language(lang)

        if not page:
            return
        self._show_toast(t("settings.language_restart_msg"), "success")

    def reset_close_preference(self, e=None):
        """Reset the 'Remember Choice' flag for the close dialog."""
        page = self._page()
        if not page:
            return
        self._app_context.settings.set_remember_close_choice(False)
        self._show_toast(t("settings.reset_close_success"), "success")

    # ------------------------------------------------------------------
    # Update flows
    # ------------------------------------------------------------------
    def check_xray_core(self, e=None):
        """Delegate Xray core updates to the shared installer runner."""
        if self._on_installer_run:
            self._on_installer_run("xray")

    def check_app_updates(self, e=None):
        """Check for app updates and drive the download/apply dialog flow."""
        page = self._page()
        if not page:
            return

        self._show_toast(t("app_update.checking"), "info")

        def check_task():
            try:
                available, current, latest, download_url = AppUpdateService.check_for_updates()

                if not available and current:
                    self._show_toast(t("app_update.up_to_date", version=current), "info")
                    return

                if available and download_url:
                    self._show_app_update_dialog(page, current, latest, download_url)
                else:
                    self._show_toast(t("app_update.check_failed"), "error")
            except Exception:
                self._show_toast(t("app_update.check_failed"), "error")

        threading.Thread(target=check_task, daemon=True).start()

    def _show_app_update_dialog(self, page, current: str, latest: str, download_url: str):
        """Show the interactive UpdateDialog with live download progress.

        An update is AVAILABLE -> modal. (Up-to-date results are reported as
        toasts by check_app_updates.)
        """
        from src.ui.components.dialogs.update_dialog import UpdateDialog

        def close_dlg(e):
            try:
                page.pop_dialog()
            except Exception:
                pass

        dlg = UpdateDialog(
            current_version=current or "?",
            latest_version=latest,
            release_notes="",
            on_update_now=lambda e: self._run_app_update_process(dlg, download_url),
            on_cancel=close_dlg,
            on_remind_later=close_dlg,
            title_text=t("app_update.title"),
        )
        page.show_dialog(dlg)

    def _run_app_update_process(self, dlg, download_url: str):
        """Run the app update process, updating the UpdateDialog in place.

        Result is reported via toast notifications on failure; a successful
        client update launches the detached updater and the app restarts.
        """
        dlg.set_status(t("app_update.downloading", progress=0))

        def update_task():
            def on_progress(progress: int):
                dlg.set_progress(progress / 100.0)
                dlg.set_status(t("app_update.downloading", progress=progress))

            zip_path = AppUpdateService.download_update(download_url, on_progress)

            if not zip_path:
                dlg.set_status(t("app_update.download_failed"))
                self._show_toast(t("app_update.download_failed"), "error")
                return

            dlg.set_status(t("app_update.extracting"))

            success = AppUpdateService.apply_update(zip_path)

            if success:
                dlg.set_status(t("app_update.restarting"))
                time.sleep(1)
                ProcessUtils.kill_process_tree()
                import os

                os._exit(0)
            else:
                dlg.set_status(t("app_update.extract_failed"))
                self._show_toast(t("app_update.extract_failed"), "error")

        threading.Thread(target=update_task, daemon=True).start()

    # ------------------------------------------------------------------
    # Rule updates (geoip / geosite)
    # ------------------------------------------------------------------
    def update_rules(self, e=None):
        """Check for and update geoip/geosite rule files."""
        page = self._page()
        if not page:
            return

        self._show_toast(t("rules_update.checking"), "info")

        def check_task():
            try:
                available, local, latest = RuleUpdateService.check_for_updates()

                if not available and local:
                    self._show_toast(t("rules_update.up_to_date"), "info")
                    return

                if available:
                    self._show_rule_update_dialog(page, latest)
                else:
                    self._show_toast(t("rules_update.check_failed"), "error")
            except Exception:
                self._show_toast(t("rules_update.check_failed"), "error")

        threading.Thread(target=check_task, daemon=True).start()

    def _show_rule_update_dialog(self, page, latest_version=None):
        """Show confirmation dialog for rule update."""
        msg = t("rules_update.message")
        if latest_version:
            msg += f"\n\nLatest: v{latest_version}"

        def close_dlg(e):
            try:
                page.pop_dialog()
            except Exception:
                pass

        def start_update(e):
            try:
                page.pop_dialog()
            except Exception:
                pass
            self._run_rule_update(page)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("rules_update.title")),
            content=ft.Text(msg),
            actions=[
                ft.TextButton(t("rules_update.cancel"), on_click=close_dlg),
                ft.ElevatedButton(t("rules_update.confirm"), on_click=start_update),
            ],
        )
        page.show_dialog(dlg)

    def _run_rule_update(self, page):
        """Run the rule update process with a progress dialog."""
        progress_ring = ft.ProgressRing(width=16, height=16, stroke_width=2)
        status_text = ft.Text(t("rules_update.installing"), size=12)

        progress_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("rules_update.title")),
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
        page.show_dialog(progress_dlg)

        def on_progress(msg):
            try:
                status_text.value = msg
                status_text.update()
            except Exception:
                pass

        def update_task():
            try:
                success = RuleUpdateService.update_rules(progress_callback=on_progress)
            finally:
                try:
                    page.pop_dialog()
                except Exception:
                    pass
            if success:
                self._show_toast(t("rules_update.success"), "success")
            else:
                self._show_toast(t("rules_update.failed"), "error")

        threading.Thread(target=update_task, daemon=True).start()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def open_routing_manager(self, e=None):
        """Open the routing rules page."""
        from src.ui.pages.routing_page import RoutingPage

        self._close_drawer()
        routing_page = RoutingPage(self._app_context, on_back=self._on_subpage_back)
        self._navigate_to(routing_page)

    def open_dns_manager(self, e=None):
        """Open the DNS settings page."""
        from src.ui.pages.dns_page import DNSPage

        self._close_drawer()
        dns_page = DNSPage(self._app_context, on_back=self._on_subpage_back)
        self._navigate_to(dns_page)

    def _close_drawer(self):
        page = self._page()
        if page:
            try:
                page.run_task(page.close_end_drawer)
            except Exception:
                pass

    def _on_subpage_back(self, e=None):
        """Handle navigation back from a subpage."""
        self._navigate_back()
