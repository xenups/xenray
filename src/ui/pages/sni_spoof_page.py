"""SNI Spoof Page — orchestrator for the SNI spoofing settings UI.

Per the project's component-driven architecture this page is purely a
coordinator: it composes the self-contained ``src/ui/components/sni/*``
components (SniHeader, SniTargetSection, SniRelaySection, SniSettingsCard),
wires their callbacks to the SniSpoofController, and reacts to the
EventBus status topic. No layout/field logic lives here.
"""

from __future__ import annotations

from typing import Optional

import flet as ft

from src.core.event_bus import TOPIC_SNI_SPOOF_CHANGED, event_bus
from src.core.i18n import get_language
from src.services.sni_spoof.sni_spoof_service import get_sni_spoof_service
from src.ui.components.sni.sni_field_row import SniStatusChip
from src.ui.components.sni.sni_header import SniHeader
from src.ui.components.sni.sni_sections import SniRelaySection, SniSettingsCard, SniTargetSection
from src.ui.controllers.sni_spoof_controller import SniSpoofController


class SniSpoofPage(ft.Container):
    """Clean, spacious, single-card SNI spoof settings page (orchestrator)."""

    def __init__(self, app_context=None, controller: Optional[SniSpoofController] = None):
        super().__init__()
        self.expand = True
        self.padding = ft.Padding.symmetric(horizontal=24, vertical=20)

        self._controller = controller or SniSpoofController(app_context=app_context)
        is_rtl = get_language() == "fa"

        # Components (sections own their fields; page only wires callbacks).
        self._header = SniHeader(
            is_rtl=is_rtl,
            enabled=self._controller.enabled,
            on_toggle_change=self._on_toggle_change,
        )
        self._target_section = SniTargetSection(
            fake_sni=self._controller.fake_sni,
            connect_ip=self._controller.connect_ip,
            connect_port=str(self._controller.connect_port),
            on_fake_sni_change=self._on_fake_sni_change,
            on_connect_ip_change=self._on_connect_ip_change,
            on_connect_port_change=self._on_connect_port_change,
        )
        self._relay_section = SniRelaySection(
            listen_host=self._controller.listen_host,
            listen_port=str(self._controller.listen_port),
            on_listen_host_change=self._on_listen_host_change,
            on_listen_port_change=self._on_listen_port_change,
        )
        self._settings_card = SniSettingsCard(
            target_section=self._target_section,
            relay_section=self._relay_section,
        )

        # Backward-compat attribute used by tests / status updates:
        # the header owns the chip; expose it here too.
        self._status_chip: SniStatusChip = self._header.status_chip

        self.content = ft.Column(
            [
                self._header,
                self._settings_card,
            ],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        # Status chip reacts to the service's status events; seed from current state or enabled setting.
        event_bus.subscribe(TOPIC_SNI_SPOOF_CHANGED, self._on_status_event)
        try:
            service = get_sni_spoof_service()
            if service and service.running:
                self.set_status(True)
            else:
                self.set_status(bool(self._controller.enabled))
        except Exception:
            self.set_status(bool(self._controller.enabled))

    def _on_status_event(self, data) -> None:
        """Apply the service's published status to the chip (Running/Stopped)."""
        if isinstance(data, dict):
            if "status" in data:
                self.set_status(data["status"] == "running")
            elif "enabled" in data and data.get("enabled_changed"):
                self.set_status(bool(data["enabled"]))

    def dispose(self) -> None:
        try:
            event_bus.unsubscribe(TOPIC_SNI_SPOOF_CHANGED, self._on_status_event)
        except Exception:
            pass

    def set_status(self, running: bool) -> None:
        """Update the status chip to Running/Stopped (heartbeat from the service)."""
        self._header.set_status(running)

    # -- Field / toggle handlers (wired into the section components) ----------
    def _on_toggle_change(self, e) -> None:
        enabled = bool(self._header.master_switch.value)
        self.set_status(enabled)
        self._controller.set_enabled(enabled)
        try:
            if self._header.master_switch.page:
                self._header.master_switch.update()
        except Exception:
            pass

    def _on_fake_sni_change(self, e) -> None:
        self._controller.set_fake_sni(self._target_section.fake_sni_field.value or "")

    def _on_connect_ip_change(self, e) -> None:
        self._controller.set_connect_ip(self._target_section.connect_ip_field.value or "")

    def _on_connect_port_change(self, e) -> None:
        try:
            self._controller.set_connect_port(int(self._target_section.connect_port_field.value or 0))
        except ValueError:
            pass

    def _on_listen_host_change(self, e) -> None:
        self._controller.set_listen_host(self._relay_section.listen_host_field.value or "")

    def _on_listen_port_change(self, e) -> None:
        try:
            self._controller.set_listen_port(int(self._relay_section.listen_port_field.value or 0))
        except ValueError:
            pass


# Backward-compatibility alias
SniSpoofView = SniSpoofPage
