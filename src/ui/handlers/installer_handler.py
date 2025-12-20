"""Installer Handler - Coordinates component installation (Xray, etc.)."""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING
import flet as ft
from src.core.i18n import t

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class InstallerHandler:
    """Handles logic for installing component updates with UI progress."""

    def __init__(self, main_window: MainWindow):
        self._main = main_window

    def run_specific_installer(self, component: str):
        """Runs the installer for a specific component with a progress dialog."""
        progress = ft.ProgressRing()
        status = ft.Text(f"Updating {component}...")

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

        self._main._page.open(dialog)

        def update_status(msg: str):
            status.value = msg
            status.update()

        def install_task():
            try:
                if component == "xray":
                    from src.services.xray_installer import XrayInstallerService

                    XrayInstallerService.install(
                        progress_callback=update_status,
                        stop_service_callback=self._main._connection_manager.disconnect,
                    )

                self._main._show_toast(t("status.update_complete", component=component), "success")
            except Exception as e:
                self._main._show_toast(t("status.update_error", error=str(e)), "error")
            finally:
                self._main._ui_helper.call(lambda: self._main._page.close(dialog))

        threading.Thread(target=install_task, daemon=True).start()
