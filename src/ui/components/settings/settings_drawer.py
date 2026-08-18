"""Settings drawer component with i18n support.

Thin composition shell: builds the presentational section components and wires their
callbacks to the SettingsHandler. No backend services are called from this file.
"""

from __future__ import annotations

import threading
from typing import Optional

import flet as ft
from loguru import logger

from src.core.app_context import AppContext
from src.core.i18n import t
from src.core.types import ConnectionMode
from src.services import task_scheduler
from src.ui.components.settings.auto_reconnect_toggle_row import AutoReconnectToggleRow
from src.ui.components.settings.base_rows import SettingsListTile, SettingsSection
from src.ui.components.settings.lan_share_toggle_row import LanShareToggleRow
from src.ui.components.settings.language_dropdown_row import LanguageDropdownRow
from src.ui.components.settings.sections import (
    AutoReconnectSection,
    ConnectivitySection,
    StartupLanguageSection,
    UpdatesSection,
)
from src.ui.components.settings.startup_toggle_row import StartupToggleRow
from src.ui.controllers.settings_controller import SettingsController
from src.ui.handlers.settings_handler import SettingsHandler


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
        fallback_toast=None,
    ):
        self._app_context = app_context
        self._on_installer_run = on_installer_run
        self._on_mode_changed = on_mode_changed
        self._get_current_mode = get_current_mode
        self._navigate_to = navigate_to
        self._navigate_back = navigate_back
        self._fallback_toast = fallback_toast

        # Backend persistence layer — validation, state mutation, EventBus emissions.
        self._settings_controller = SettingsController(
            app_context=self._app_context,
            toast_callback=self._show_toast,
        )

        # Orchestration layer — update flows, dialogs, navigation, save handling.
        self._handler = SettingsHandler(
            app_context=self._app_context,
            controller=self._settings_controller,
            show_toast=self._show_toast,
            get_page=lambda: self.safe_page,
            on_mode_changed=self._on_mode_changed,
            navigate_to=self._navigate_to,
            navigate_back=self._navigate_back,
            on_installer_run=self._on_installer_run,
        )

        # Mode state
        current_mode = self._get_current_mode()
        is_proxy = current_mode == ConnectionMode.PROXY

        # Self-contained rows (manage their own state / EventBus subscriptions)
        self._lan_share_row = LanShareToggleRow(
            app_context=self._app_context,
            toast_callback=self._show_toast,
        )
        self._auto_reconnect_row = AutoReconnectToggleRow(
            app_context=self._app_context,
            toast_callback=self._show_toast,
        )
        self._startup_row = StartupToggleRow(
            app_context=self._app_context,
            is_registered=task_scheduler.is_task_registered(),
            is_supported=task_scheduler.is_supported(),
            on_register=task_scheduler.register_task,
            on_unregister=task_scheduler.unregister_task,
            toast_callback=self._show_toast,
        )
        self._language_row = LanguageDropdownRow(
            self._app_context.settings.get_language(),
            self._on_language_change,
        )

        # Presentational sections
        self._connectivity_section = ConnectivitySection(
            is_proxy=is_proxy,
            on_mode_change=self._on_mode_change,
            proxy_port=self._app_context.settings.get_proxy_port(),
            on_save_port=self._on_save_port,
            http_port=self._app_context.settings.get_http_port(),
            on_save_http_port=self._on_save_http_port,
            country_code=self._app_context.settings.get_routing_country(),
            on_country_change=self._on_country_change,
            tun_engine=self._app_context.settings.get_tun_engine(),
            on_tun_engine_change=self._on_tun_engine_change,
            lan_share_row=self._lan_share_row,
        )
        self._auto_reconnect_section = AutoReconnectSection(self._auto_reconnect_row)
        self._startup_language_section = StartupLanguageSection(
            self._startup_row,
            self._language_row,
        )
        self._updates_section = UpdatesSection(
            on_check_app_updates=self._handler.check_app_updates,
            on_check_xray_core=self._handler.check_xray_core,
            on_update_rules=self._handler.update_rules,
        )

        # Version text ref — populated lazily in background to avoid
        # blocking subprocess calls (xray -version) at init time.
        self._xray_version_text = ft.Text(
            "Xray: v...",
            size=11,
            color=ft.Colors.OUTLINE,
        )

        app_section = SettingsSection(
            t("settings.application"),
            [
                self._startup_language_section,
                self._auto_reconnect_section,
                SettingsListTile(
                    ft.Icons.ROUTE,
                    t("settings.routing_rules"),
                    t("settings.routing_description"),
                    on_click=self._handler.open_routing_manager,
                ),
                SettingsListTile(
                    ft.Icons.DNS,
                    t("settings.dns_manager"),
                    t("settings.dns_description"),
                    on_click=self._handler.open_dns_manager,
                ),
                SettingsListTile(
                    ft.Icons.RESTART_ALT,
                    t("settings.reset_close_choice"),
                    t("settings.reset_close_choice_desc"),
                    on_click=self._handler.reset_close_preference,
                ),
            ],
        )

        version_footer = ft.Container(
            content=ft.Row(
                [self._xray_version_text],
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            padding=20,
        )

        # Build UI — glass container wrapping all content
        settings_content = ft.Column(
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
                # Scrollable content including version footer
                ft.Column(
                    [
                        self._connectivity_section,
                        ft.Divider(
                            height=1,
                            color=ft.Colors.OUTLINE_VARIANT,
                            opacity=0.2,
                        ),
                        ft.Container(height=10),
                        app_section,
                        ft.Divider(
                            height=1,
                            color=ft.Colors.OUTLINE_VARIANT,
                            opacity=0.2,
                        ),
                        ft.Container(height=10),
                        self._updates_section,
                        # Version Footer inside scrollable area
                        version_footer,
                    ],
                    scroll=ft.ScrollMode.HIDDEN,
                    expand=True,
                    spacing=0,
                ),
            ],
            spacing=0,
            expand=True,
        )

        glass_content = ft.Container(
            content=settings_content,
            bgcolor=ft.Colors.with_opacity(0.7, "#0f172a"),
            blur=ft.Blur(20, 20, ft.BlurTileMode.MIRROR),
            expand=True,
        )

        drawer_container = ft.Container(
            content=glass_content,
            width=320,
            expand=True,
        )

        super().__init__(
            controls=[drawer_container],
            bgcolor=ft.Colors.TRANSPARENT,
            shadow_color=ft.Colors.TRANSPARENT,
            on_change=self._on_drawer_change,
        )

        # Start version refresh in background so texts populate when drawer opens
        threading.Thread(target=self._refresh_versions, daemon=True).start()

    # ------------------------------------------------------------------
    # Version refresh (lazy, non-blocking)
    # ------------------------------------------------------------------
    def _on_drawer_change(self, e=None):
        """Fired when the drawer opens/closes — refresh versions."""
        threading.Thread(target=self._refresh_versions, daemon=True).start()

    def _refresh_versions(self):
        """Read installed Xray version in a background thread and update UI."""
        new_xray = self._handler.get_xray_version()

        if self._xray_version_text.value != new_xray:
            self._xray_version_text.value = new_xray
            try:
                if self._xray_version_text.page:
                    self._xray_version_text.update()
            except Exception:
                pass

    def _close_drawer(self, e=None):
        """Close this settings drawer."""
        page = self.safe_page
        if page is not None:
            try:
                page.run_task(page.close_end_drawer)
            except Exception:
                pass

    @property
    def safe_page(self) -> Optional[ft.Page]:
        """RuntimeError-safe page property getter."""
        try:
            return self.page
        except (RuntimeError, AttributeError):
            return None

    def _show_toast(self, message: str, message_type: str = "info"):
        """Show a toast notification.

        If the drawer is not yet mounted (no safe_page — e.g. the Settings TAB
        triggers an update before the drawer was ever opened), fall back to the
        always-alive MainWindow toast instead of silently dropping it.
        """
        page = self.safe_page
        if page and hasattr(page, "_toast_manager"):
            page._toast_manager.show(message, message_type)
        elif page:
            logger.warning("Toast manager not available, message not shown")
        elif self._fallback_toast:
            self._fallback_toast(message, message_type)

    # ------------------------------------------------------------------
    # Callback wiring (presentation -> handler)
    # ------------------------------------------------------------------
    def _on_mode_change(self, e):
        self._handler.handle_mode_change(self._connectivity_section.mode_switch_row, e)

    def _on_save_port(self, value):
        self._handler.save_port(self._connectivity_section.port_row, value)

    def _on_save_http_port(self, value):
        self._handler.save_http_port(self._connectivity_section.http_port_row, value)

    def _on_country_change(self, val):
        self._handler.save_country(self._connectivity_section.country_row, val)

    def _on_tun_engine_change(self, e):
        self._handler.save_tun_engine(self._connectivity_section.tun_dropdown_row, e)

    def _on_language_change(self, e):
        self._handler.save_language(self._language_row, e)
