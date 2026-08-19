"""Settings Page Component matching Slate Dark & Electric Cyan design specs."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import t
from src.ui.components.settings import (
    AutoReconnectToggleRow,
    BentoCard,
    CountryDropdownRow,
    HttpPortInputRow,
    LanguageDropdownRow,
    LanShareToggleRow,
    ModeSwitchRow,
    PortInputRow,
    SectionHeader,
    SettingsListTile,
    StartupToggleRow,
    TunEngineRow,
    UpdateCard,
)
from src.ui.theme import GlassTokens


class SettingsPage(ft.Container):
    """Modern Bento Grid Settings Page based on Stitch specs."""

    def __init__(
        self,
        mode_switch_row: ModeSwitchRow,
        tun_engine_row: TunEngineRow,
        port_row: PortInputRow,
        country_row: CountryDropdownRow,
        language_row: LanguageDropdownRow,
        reconnect_row: AutoReconnectToggleRow,
        startup_row: StartupToggleRow,
        on_check_update_click: Optional[Callable] = None,
        on_check_core_click: Optional[Callable] = None,
        settings_controller: Optional[object] = None,
        on_open_routing_click: Optional[Callable] = None,
        on_open_dns_click: Optional[Callable] = None,
        lan_share_row: Optional[LanShareToggleRow] = None,
        http_port_row: Optional[HttpPortInputRow] = None,
        routing_badge_text: str = "12 Active Rules",
        dns_badge_text: str = "Cloudflare (1.1.1.1)",
    ):
        self._mode_switch_row = mode_switch_row
        self._tun_engine_row = tun_engine_row
        self._port_row = port_row
        self._http_port_row = http_port_row
        self._country_row = country_row
        self._language_row = language_row
        self._reconnect_row = reconnect_row
        self._startup_row = startup_row
        self._lan_share_row = lan_share_row
        self._on_check_update_click = on_check_update_click
        self._on_check_core_click = on_check_core_click
        self._settings_controller = settings_controller
        self._on_open_routing_click = on_open_routing_click
        self._on_open_dns_click = on_open_dns_click

        connectivity_controls = [
            SectionHeader(
                ft.Icons.WIFI_TETHERING,
                t("settings.connectivity_title", default="Connectivity Settings"),
            ),
            self._mode_switch_row,
            self._port_row,
        ]

        if self._http_port_row:
            connectivity_controls.append(self._http_port_row)

        if self._lan_share_row:
            connectivity_controls.append(self._lan_share_row)

        connectivity_controls.append(self._tun_engine_row)

        self._connectivity_card = BentoCard(controls=connectivity_controls)

        routing_controls = [
            SectionHeader(
                ft.Icons.ALT_ROUTE,
                t("settings.routing_title", default="Routing & Anti-Leak"),
            ),
            self._country_row,
        ]

        if self._on_open_routing_click:
            routing_controls.append(
                SettingsListTile(
                    ft.Icons.ROUTE,
                    t("settings.routing_rules", default="Custom Routing Rules"),
                    t(
                        "settings.routing_description",
                        default="Configure custom domain and IP routing rules",
                    ),
                    on_click=self._on_open_routing_click,
                    badge_text=routing_badge_text,
                )
            )

        if self._on_open_dns_click:
            routing_controls.append(
                SettingsListTile(
                    ft.Icons.DNS,
                    t("settings.dns_manager", default="DNS Management"),
                    t(
                        "settings.dns_description",
                        default="Configure custom DNS servers and resolution strategies",
                    ),
                    on_click=self._on_open_dns_click,
                    badge_text=dns_badge_text,
                )
            )

        self._routing_card = BentoCard(controls=routing_controls)

        self._preferences_card = BentoCard(
            controls=[
                SectionHeader(
                    ft.Icons.TUNE,
                    t("settings.preferences_title", default="Application Preferences"),
                ),
                self._language_row,
                self._reconnect_row,
                self._startup_row,
            ]
        )

        def _handle_update_click(e):
            page_ref = getattr(e, "page", None)
            if not page_ref and hasattr(self, "page"):
                page_ref = self.page

            try:
                if self._settings_controller:
                    self._settings_controller.check_for_updates(
                        update_card_ref=self._update_card,
                        page_ref=page_ref,
                    )
                elif self._on_check_update_click:
                    self._on_check_update_click(e)
            except Exception as err:
                from src.core.logger import logger
                from src.ui.components.common.toast import ToastManager

                logger.error(f"[SettingsPage] Error in App update click: {err}")
                ToastManager.show_error(page_ref, f"Update check error: {err}")

        self._update_card = UpdateCard(on_check_update_click=_handle_update_click)

        def _handle_core_update_click(e):
            page_ref = getattr(e, "page", None)
            if not page_ref and hasattr(self, "page"):
                page_ref = self.page

            try:
                if self._on_check_core_click:
                    self._on_check_core_click(e)
                elif self._settings_controller:
                    self._settings_controller.check_xray_core_update(
                        core_card_ref=self._xray_core_card,
                        page_ref=page_ref,
                    )
            except Exception as err:
                from src.core.logger import logger
                from src.ui.components.common.toast import ToastManager

                logger.error(f"[SettingsPage] Error in Core update click: {err}")
                ToastManager.show_error(page_ref, f"Xray-Core update check error: {err}")

        from src.ui.components.settings.xray_core_card import XrayCoreCard

        self._xray_core_card = XrayCoreCard(on_check_core_click=_handle_core_update_click)

        super().__init__(
            content=ft.Column(
                [
                    self._connectivity_card,
                    self._routing_card,
                    self._preferences_card,
                    self._update_card,
                    self._xray_core_card,
                ],
                spacing=14,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            padding=ft.Padding.only(left=20, right=20, top=20, bottom=16),
            expand=True,
            bgcolor=GlassTokens.BG_PAGE,
        )

    def did_mount(self) -> None:
        """Sync component state from repository on mount."""
        try:
            if hasattr(self, "_app_context") and self._app_context:
                direct_country = self._app_context.settings.get_direct_country()
                if self._country_row and hasattr(self._country_row, "_dropdown"):
                    self._country_row._dropdown.value = direct_country if direct_country else "none"
                    if self._country_row.page:
                        self._country_row.update()
        except Exception:
            pass

    def update_labels(self) -> None:
        """Refresh dynamic component translations on language change."""
        if hasattr(self._update_card, "update_labels"):
            self._update_card.update_labels()
        if hasattr(self._xray_core_card, "update_labels"):
            self._xray_core_card.update_labels()


# Backward-compatibility alias
SettingsView = SettingsPage
