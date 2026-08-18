"""SNI Spoof View - dedicated full-page settings view for the SNI spoofing feature."""

from __future__ import annotations

from typing import Optional

import flet as ft

from src.core.event_bus import TOPIC_SNI_SPOOF_CHANGED, event_bus
from src.core.i18n import t
from src.services.sni_spoof.sni_spoof_service import get_sni_spoof_service
from src.ui.controllers.sni_spoof_controller import SniSpoofController


class SniSpoofView(ft.Container):
    """Full-page SNI spoof settings view (header, master toggle, connection fields, status chip)."""

    def __init__(
        self, app_context=None, controller: Optional[SniSpoofController] = None
    ):
        super().__init__()
        self.expand = True
        self.padding = ft.Padding.only(left=20, right=20, top=20, bottom=16)

        self._controller = controller or SniSpoofController(app_context=app_context)

        self._master_switch = ft.Switch(
            value=self._controller.enabled,
            active_color="#4ADE80",
            on_change=self._on_toggle_change,
        )

        # Top-priority fields: save-on-change, persisted via the controller.
        self._fake_sni_field = ft.TextField(
            value=self._controller.fake_sni,
            label=t("sni_spoof.fake_sni", default="FAKE SNI"),
            hint_text="chatgpt.com",
            border_radius=10,
            on_change=self._on_fake_sni_change,
        )
        self._connect_ip_field = ft.TextField(
            value=self._controller.connect_ip,
            label=t("sni_spoof.connect_ip", default="CONNECT IP"),
            hint_text="185.193.30.94",
            border_radius=10,
            on_change=self._on_connect_ip_change,
        )

        # Secondary fields (local relay listen address).
        self._connect_port_field = ft.TextField(
            value=str(self._controller.connect_port),
            label=t("sni_spoof.connect_port", default="CONNECT PORT"),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            border_radius=10,
            on_change=self._on_connect_port_change,
        )
        self._listen_host_field = ft.TextField(
            value=self._controller.listen_host,
            label=t("sni_spoof.listen_host", default="LISTEN HOST"),
            hint_text="127.0.0.1",
            border_radius=10,
            on_change=self._on_listen_host_change,
        )
        self._listen_port_field = ft.TextField(
            value=str(self._controller.listen_port),
            label=t("sni_spoof.listen_port", default="LISTEN PORT"),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=180,
            border_radius=10,
            on_change=self._on_listen_port_change,
        )

        # Status chip: Running / Stopped placeholder (heartbeat wired by WS2/WS3).
        self._status_chip = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        width=8,
                        height=8,
                        border_radius=4,
                        bgcolor=ft.Colors.with_opacity(0.5, "#f87171"),
                    ),
                    ft.Text(
                        t("sni_spoof.stopped", default="Stopped"),
                        size=11,
                        weight=ft.FontWeight.W_600,
                        color="#f87171",
                    ),
                ],
                spacing=6,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.12, "#f87171"),
        )

        field_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        t("sni_spoof.connection_title", default="Connection"),
                        size=14,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.WHITE,
                    ),
                    self._fake_sni_field,
                    self._connect_ip_field,
                    ft.Row(
                        [
                            self._connect_port_field,
                            self._listen_host_field,
                            self._listen_port_field,
                        ],
                        spacing=10,
                        wrap=True,
                    ),
                ],
                spacing=10,
            ),
            padding=16,
            border_radius=16,
            border=ft.Border.all(1, "#212836"),
            bgcolor="#151a23",
        )

        header_row = ft.Row(
            [
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.SHIELD_ROUNDED, size=20, color="#6d28d9"
                                ),
                                ft.Text(
                                    t("sni_spoof.title", default="SNI Spoof"),
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.WHITE,
                                ),
                            ],
                            spacing=8,
                        ),
                        ft.Text(
                            t(
                                "sni_spoof.subtitle",
                                default="Hide the real SNI from DPI by sending a fake TLS Server Name",
                            ),
                            size=11,
                            color="#8E8C99",
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                self._master_switch,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.content = ft.Column(
            [
                header_row,
                self._status_chip,
                field_card,
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        # Status chip reacts to the service's status events; seed from current state.
        event_bus.subscribe(TOPIC_SNI_SPOOF_CHANGED, self._on_status_event)
        try:
            self.set_status(get_sni_spoof_service().running)
        except Exception:
            pass

    def _on_status_event(self, data) -> None:
        """Apply the service's published status to the chip (Running/Stopped)."""
        if isinstance(data, dict) and "status" in data:
            self.set_status(data["status"] == "running")

    def dispose(self) -> None:
        try:
            event_bus.unsubscribe(TOPIC_SNI_SPOOF_CHANGED, self._on_status_event)
        except Exception:
            pass

    def set_status(self, running: bool) -> None:
        """Update the status chip to Running/Stopped (heartbeat from the service)."""
        color = "#4ADE80" if running else "#f87171"
        row = self._status_chip.content
        self._status_chip.bgcolor = ft.Colors.with_opacity(0.12, color)
        row.controls[0].bgcolor = ft.Colors.with_opacity(0.5, color)
        row.controls[1].value = t(
            "sni_spoof.running" if running else "sni_spoof.stopped",
            default="Running" if running else "Stopped",
        )
        row.controls[1].color = color
        try:
            if self._status_chip.page:
                self._status_chip.update()
        except Exception:
            pass

    def _on_toggle_change(self, e) -> None:
        self._controller.set_enabled(self._master_switch.value)
        try:
            if self._master_switch.page:
                self._master_switch.update()
        except Exception:
            pass

    def _on_fake_sni_change(self, e) -> None:
        self._controller.set_fake_sni(self._fake_sni_field.value or "")

    def _on_connect_ip_change(self, e) -> None:
        self._controller.set_connect_ip(self._connect_ip_field.value or "")

    def _on_connect_port_change(self, e) -> None:
        try:
            self._controller.set_connect_port(int(self._connect_port_field.value or 0))
        except ValueError:
            pass

    def _on_listen_host_change(self, e) -> None:
        self._controller.set_listen_host(self._listen_host_field.value or "")

    def _on_listen_port_change(self, e) -> None:
        try:
            self._controller.set_listen_port(int(self._listen_port_field.value or 0))
        except ValueError:
            pass


# Backward-compatibility alias
SniSpoofPage = SniSpoofView
