"""Settings drawer component with i18n support."""

from __future__ import annotations

import threading

import flet as ft
from loguru import logger

from src.core.app_context import AppContext
from src.core.constants import APP_VERSION
from src.core.i18n import t
from src.core.types import ConnectionMode
from src.services import task_scheduler
from src.services.app_update_service import AppUpdateService
from src.services.rule_update_service import RuleUpdateService
from src.services.xray_installer import XrayInstallerService
from src.ui.components.settings.settings_form_presenter import SettingsFormPresenter
from src.ui.components.settings_sections import (
    AutoReconnectToggleRow,
    CountryDropdownRow,
    LanguageDropdownRow,
    ModeRadioCards,
    PortInputRow,
    SettingsListTile,
    SettingsSection,
    StartupToggleRow,
    TunEngineRow,
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

        self._presenter = SettingsFormPresenter(self._app_context, self._show_toast)

        current_mode = self._get_current_mode()
        self._is_proxy = current_mode == ConnectionMode.PROXY

        self._mode_cards = ModeRadioCards(self._is_proxy, self._handle_mode_change)
        self._port_row = PortInputRow(
            self._app_context.settings.get_proxy_port(),
            self._presenter.save_port,
        )
        self._country_row = CountryDropdownRow(
            self._app_context.settings.get_routing_country(),
            self._presenter.save_country,
        )
        self._tun_engine_row = TunEngineRow(
            self._app_context.settings.get_tun_engine(),
            self._presenter.save_tun_engine,
        )
        self._tun_engine_row.visible = not self._is_proxy
        self._language_row = LanguageDropdownRow(
            self._app_context.settings.get_language(),
            self._presenter.save_language,
        )

        self._startup_row = StartupToggleRow(
            app_context=self._app_context,
            is_registered=task_scheduler.is_task_registered(),
            is_supported=task_scheduler.is_supported(),
            on_register=task_scheduler.register_task,
            on_unregister=task_scheduler.unregister_task,
            toast_callback=self._show_toast,
        )

        self._auto_reconnect_row = AutoReconnectToggleRow(
            app_context=self._app_context,
            toast_callback=self._show_toast,
        )

        self._xray_version_text = ft.Text(
            "Xray: v...",
            size=11,
            color=ft.Colors.OUTLINE,
        )

        settings_content = ft.Column(
            [
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
                ft.Column(
                    [
                        SettingsSection(
                            t("settings.connection"),
                            [
                                self._mode_cards,
                                self._tun_engine_row,
                                self._port_row,
                                self._country_row,
                            ],
                        ),
                        ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.2),
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
                                    on_click=lambda e: self._presenter.reset_close_preference(),
                                ),
                            ],
                        ),
                        ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.2),
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
                                    ft.Icons.PUBLIC,
                                    t("settings.update_rules"),
                                    t("settings.update_rules_desc"),
                                    on_click=self._update_rules,
                                ),
                                SettingsListTile(
                                    ft.Icons.INFO_OUTLINE,
                                    t("settings.about"),
                                    f"v{APP_VERSION} by Xenups",
                                    show_chevron=False,
                                ),
                            ],
                        ),
                        ft.Container(
                            content=ft.Column(
                                [
                                    self._xray_version_text,
                                    ft.Text(
                                        f"App: v{APP_VERSION}",
                                        size=11,
                                        color=ft.Colors.OUTLINE,
                                    ),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=2,
                            ),
                            padding=ft.Padding.symmetric(vertical=15),
                            alignment=ft.Alignment.CENTER,
                        ),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
            ],
            expand=True,
        )

        super().__init__(
            controls=[
                ft.Container(
                    content=settings_content,
                    padding=10,
                    width=340,
                    expand=True,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                )
            ],
        )

        self._load_xray_version_async()

    def _close_drawer(self, e=None):
        try:
            if self.page:
                self.page.close(self)
        except Exception:
            pass

    def _handle_mode_change(self, is_proxy: bool):
        new_mode = ConnectionMode.PROXY if is_proxy else ConnectionMode.VPN

        if new_mode == ConnectionMode.VPN and not ProcessUtils.is_admin():
            self._show_toast(t("status.admin_required"), "warning")
            self._mode_cards.value = True
            return

        self._is_proxy = is_proxy
        self._tun_engine_row.visible = not is_proxy

        mode_str = "proxy" if is_proxy else "vpn"
        self._app_context.settings.set_connection_mode(mode_str)
        self._on_mode_changed(new_mode)

        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def _open_routing_manager(self, e=None):
        from src.ui.pages.routing_page import RoutingPage

        if self._navigate_to:
            routing_page = RoutingPage(self._app_context, self._navigate_back)
            self._navigate_to(routing_page)
        self._close_drawer()

    def _open_dns_manager(self, e=None):
        from src.ui.pages.dns_page import DNSPage

        if self._navigate_to:
            dns_page = DNSPage(self._app_context, self._navigate_back)
            self._navigate_to(dns_page)
        self._close_drawer()

    def _check_app_updates(self, e=None):
        self._show_toast(t("settings.checking_app_updates"), "info")

        def _task():
            has_update, latest_ver, download_url = AppUpdateService.check_for_updates()
            if has_update:
                self._show_toast(t("settings.app_update_found", version=latest_ver), "success")
            else:
                self._show_toast(t("settings.app_up_to_date"), "info")

        threading.Thread(target=_task, daemon=True).start()

    def _update_rules(self, e=None):
        self._show_toast(t("settings.updating_rules"), "info")

        def _task():
            success, msg = RuleUpdateService.update_all_rules()
            if success:
                self._show_toast(t("settings.rules_updated"), "success")
            else:
                self._show_toast(t("settings.rules_update_failed", error=msg), "error")

        threading.Thread(target=_task, daemon=True).start()

    def _on_installer_run(self, component: str):
        self._on_installer_run_external(component)

    def _load_xray_version_async(self):
        def _task():
            from src.core.constants import XRAY_VERSION

            version_str = XRAY_VERSION if XrayInstallerService.is_installed() else None
            display_str = f"Xray: v{version_str}" if version_str else "Xray: " + t("status.not_installed")

            def _update_ui():
                self._xray_version_text.value = display_str
                try:
                    if self._xray_version_text.page:
                        self._xray_version_text.update()
                except Exception:
                    pass

            try:
                _update_ui()
            except Exception:
                pass

        threading.Thread(target=_task, daemon=True).start()

    def _show_toast(self, message: str, message_type: str = "info"):
        pg = None
        try:
            pg = self.page
        except Exception:
            pg = getattr(self, "_page", None)

        if pg and hasattr(pg, "_toast_manager") and pg._toast_manager:
            tm = pg._toast_manager
            method = getattr(tm, message_type, None) or getattr(tm, "info", None) or getattr(tm, "show", None)
            if method:
                try:
                    method(message)
                except Exception:
                    pass
