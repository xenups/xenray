"""Connectivity settings section - mode toggle, proxy ports, LAN sharing, and TUN engine."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.ui.components.settings.base_rows import SettingsSection
from src.ui.components.settings.country_dropdown_row import CountryDropdownRow
from src.ui.components.settings.engine_rows import TunEngineDropdownRow
from src.ui.components.settings.lan_share_toggle_row import LanShareToggleRow
from src.ui.components.settings.mode_switch_row import ModeSwitchRow
from src.ui.components.settings.port_input_row import HttpPortInputRow, PortInputRow


class ConnectivitySection(ft.Container):
    """Connection settings section composing the mode switch, SOCKS/HTTP ports, direct
    country, LAN sharing toggle, and TUN engine selector rows."""

    def __init__(
        self,
        *,
        is_proxy: bool,
        on_mode_change: Callable,
        proxy_port: int,
        on_save_port: Callable,
        http_port: int,
        on_save_http_port: Callable,
        country_code: str,
        on_country_change: Callable,
        tun_engine: str,
        on_tun_engine_change: Callable,
        lan_share_row: LanShareToggleRow,
    ):
        self._mode_switch_row = ModeSwitchRow(is_proxy, on_mode_change)
        self._port_row = PortInputRow(proxy_port, on_save_port)
        self._http_port_row = HttpPortInputRow(http_port, on_save_http_port)
        self._country_row = CountryDropdownRow(country_code, on_country_change)
        self._tun_dropdown_row = TunEngineDropdownRow(tun_engine, on_tun_engine_change)
        self._lan_share_row = lan_share_row

        super().__init__(
            content=SettingsSection(
                t("settings.connection"),
                [
                    self._mode_switch_row,
                    self._port_row,
                    self._http_port_row,
                    self._country_row,
                    self._lan_share_row,
                    self._tun_dropdown_row,
                ],
            )
        )

    @property
    def mode_switch_row(self) -> ModeSwitchRow:
        return self._mode_switch_row

    @property
    def port_row(self) -> PortInputRow:
        return self._port_row

    @property
    def http_port_row(self) -> HttpPortInputRow:
        return self._http_port_row

    @property
    def country_row(self) -> CountryDropdownRow:
        return self._country_row

    @property
    def tun_dropdown_row(self) -> TunEngineDropdownRow:
        return self._tun_dropdown_row

    @property
    def lan_share_row(self) -> LanShareToggleRow:
        return self._lan_share_row
