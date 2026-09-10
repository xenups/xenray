"""Installer Handler - Coordinates component installation (Xray, etc.)."""

from __future__ import annotations

import threading
from typing import Optional

import flet as ft

from src.core.connection_manager import ConnectionManager
from src.core.i18n import t


class InstallerHandler:
    """Handles logic for installing component updates with UI progress."""

    def __init__(self, connection_manager: ConnectionManager):
        self._connection_manager = connection_manager
        self._page: Optional[ft.Page] = None
        self._ui_helper = None
        self._toast = None

    def setup(self, page: ft.Page, ui_helper, toast):
        """Bind UI components to the handler."""
        self._page = page
        self._ui_helper = ui_helper
        self._toast = toast

    def run_specific_installer(self, component: str):
        """Runs the installer for a specific component with a progress dialog."""
        if not self._page:
            return

        progress = ft.ProgressRing()
        status = ft.Text(f"{t('status.updating')} {component}...")

        # Create a modal dialog
        dialog = ft.AlertDialog(
            content=ft.Column(
                [progress, status],
                alignment=ft.MainAxisAlignment.CENTER,
                height=100,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            modal=True,
        )

        self._page.show_dialog(dialog)

        def update_status(msg: str):
            status.value = msg
            status.update()

        def install_task():
            try:
                if component == "xray":
                    from src.services.installer.xray_installer import XrayInstallerService

                    XrayInstallerService.install(
                        progress_callback=update_status,
                        stop_service_callback=self._connection_manager.disconnect,
                    )
                elif component in ("singbox", "sing-box"):
                    from src.services.installer.singbox_installer import SingboxInstallerService

                    SingboxInstallerService.install(
                        progress_callback=update_status,
                        stop_service_callback=self._connection_manager.disconnect,
                    )

                if self._toast:
                    self._toast.show(t("status.update_complete", component=component), "success")
            except PermissionError as pe:
                err_msg = str(pe)
                if self._toast:
                    self._toast.show(err_msg, "error")
                from src.utils.process_utils import ProcessUtils

                if not ProcessUtils.is_admin() and self._page and self._ui_helper:

                    def _show_admin_prompt():
                        def close_d(e):
                            try:
                                self._page.pop_dialog()
                            except Exception:
                                pass

                        def restart_d(e):
                            try:
                                self._page.pop_dialog()
                            except Exception:
                                pass
                            ProcessUtils.restart_as_admin()

                        d = ft.AlertDialog(
                            modal=True,
                            title=ft.Text(t("admin.title", default="Administrator Privileges Required")),
                            content=ft.Text(err_msg),
                            actions=[
                                ft.TextButton(t("admin.cancel", default="Cancel"), on_click=close_d),
                                ft.TextButton(t("admin.restart", default="Restart as Admin"), on_click=restart_d),
                            ],
                            actions_alignment=ft.MainAxisAlignment.END,
                        )
                        self._page.show_dialog(d)

                    self._ui_helper.call(_show_admin_prompt)
            except Exception as e:
                if self._toast:
                    self._toast.show(t("status.update_error", error=str(e)), "error")
            finally:
                if self._ui_helper:

                    def _safe_close():
                        if self._page:
                            try:
                                _attached = dialog.page is not None
                            except RuntimeError:
                                _attached = False
                            if _attached:
                                try:
                                    self._page.pop_dialog()
                                except Exception:
                                    pass

                    self._ui_helper.call(_safe_close)

        threading.Thread(target=install_task, daemon=True).start()
