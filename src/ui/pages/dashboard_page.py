"""Dashboard Page – connection centerpiece + active server hero + dynamic wave footer."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.event_bus import (
    TOPIC_ACTIVE_SERVER_PING_UPDATED,
    TOPIC_CONNECTION_STATE_CHANGED,
    TOPIC_SERVER_INSPECTED,
    TOPIC_TELEMETRY_UPDATED,
    EngineEvent,
    event_bus,
)
from src.core.i18n import t
from src.ui.components.dashboard.connection_button import ConnectionButton
from src.ui.components.dashboard.traffic_cards import TrafficCards
from src.ui.controllers.dashboard_controller import DashboardController, DashboardState
from src.ui.helpers.status_helper import get_short_status_label
from src.ui.theme import GlassTokens


class DashboardPage(ft.Container):
    """Dashboard Page – central connection hero with server title/flag and dynamic wave visualizer."""

    def __init__(
        self,
        on_toggle_click: Callable,
        on_change_server_click: Callable,
        on_open_statistics_click: Optional[Callable] = None,
        connection_button: Optional[ConnectionButton] = None,
        app_context=None,
        server_card=None,
    ):
        self._on_toggle_click = on_toggle_click
        self._on_change_server_click = on_change_server_click
        self._on_open_statistics_click = on_open_statistics_click
        self._app_context = app_context
        self._server_card_component = server_card

        self._is_connected = False
        self._is_connecting = False
        self._is_disconnecting = False
        self._is_online = True
        self._lan_sharing_enabled = False

        self._toggle_button = (
            connection_button if connection_button is not None else ConnectionButton(on_click=self._on_toggle_click)
        )

        self._controller = DashboardController(
            on_state_changed=self._on_controller_state_changed,
            on_uptime_updated=self.update_uptime,
            on_stats_updated=self._on_controller_stats_updated,
        )

        event_bus.subscribe(TOPIC_TELEMETRY_UPDATED, self._on_telemetry_event)
        event_bus.subscribe(TOPIC_CONNECTION_STATE_CHANGED, self._on_connection_state_event)
        event_bus.subscribe(TOPIC_ACTIVE_SERVER_PING_UPDATED, self._on_active_server_ping_updated)
        event_bus.subscribe(TOPIC_SERVER_INSPECTED, self._on_server_inspected)

        # 1. Active Server Title and Location Details (Balanced, Clean Typography)
        self._server_name_text = ft.Text(
            t("server_list.no_server"),
            font_family="Segoe UI Light",
            size=36,
            weight=ft.FontWeight.W_300,
            style=ft.TextStyle(letter_spacing=1.0),
            color="#FFFFFF",
            text_align=ft.TextAlign.CENTER,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self._server_flag_text = ft.Text(
            "",
            size=16,
            visible=False,
            text_align=ft.TextAlign.CENTER,
        )

        self._server_location_text = ft.Text(
            "",
            font_family="Segoe UI Light",
            size=13,
            weight=ft.FontWeight.W_300,
            style=ft.TextStyle(letter_spacing=0.8),
            color=ft.Colors.with_opacity(0.65, ft.Colors.WHITE),
            text_align=ft.TextAlign.CENTER,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self._server_location_row = ft.Row(
            controls=[
                self._server_location_text,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._server_info_container = ft.Container(
            content=ft.Column(
                [
                    self._server_name_text,
                    self._server_location_row,
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            margin=ft.Margin(left=0, right=10, top=0, bottom=0),
            padding=ft.Padding.symmetric(horizontal=24, vertical=6),
            border_radius=12,
            bgcolor=ft.Colors.TRANSPARENT,
            on_click=lambda e: (self._on_change_server_click(e) if self._on_change_server_click else None),
            tooltip=t("server_list.change_server", default="Change Server"),
        )

        # Backward compatibility traffic cards reference
        self._traffic_cards = TrafficCards(on_card_click=self._on_open_statistics_click)

        # Initialize active server info from app_context if present
        self._init_server_info_from_context()
        hero_center_section = ft.Container(
            content=ft.Column(
                [
                    ft.Container(height=75),
                    self._toggle_button,
                    ft.Container(height=18),
                    self._server_info_container,
                ],
                alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            alignment=ft.Alignment.TOP_CENTER,
            margin=ft.Margin(left=0, right=25, top=0, bottom=0),
            expand=True,
        )

        self._wave_visualizer = None

        super().__init__(
            content=hero_center_section,
            padding=0,
            expand=True,
            bgcolor=GlassTokens.BG_PAGE,
        )

    @classmethod
    def _extract_location_details(
        cls,
        profile: Optional[dict] = None,
        country_code: str = "",
        country_name: str = "",
    ) -> tuple[str, str]:
        """Extract emoji flag and formatted 'City, Country' or 'Country' string."""
        from src.core.country_translator import translate_country

        profile = profile or {}
        name = profile.get("name", "")
        cc = country_code or profile.get("country_code", "")
        cname = country_name or profile.get("country_name", "")
        city = profile.get("city", "") if isinstance(profile, dict) else ""

        if not cc and name:
            from src.utils.country_flags import extract_country_code_from_name

            cc = extract_country_code_from_name(name) or ""

        resolved_country = translate_country(cc, fallback=cname) if cc else (cname or "")

        if resolved_country and city:
            loc_str = f"{resolved_country}, {city}"
        elif resolved_country:
            loc_str = resolved_country
        elif city:
            loc_str = city
        elif cc:
            loc_str = cc.upper()
        else:
            loc_str = t("server_list.unknown_location", default="Unknown Location") if name else ""

        return "", loc_str

    def _init_server_info_from_context(self) -> None:
        """Initialize active server display from app context if available."""
        if not self._app_context:
            return
        try:
            selected_pid = getattr(self._app_context, "selected_profile_id", None)
            if hasattr(self._app_context, "settings"):
                selected_pid = selected_pid or self._app_context.settings.get_last_selected_profile_id()
            if selected_pid and hasattr(self._app_context, "get_profile_by_id"):
                profile = self._app_context.get_profile_by_id(selected_pid)
                if profile:
                    name = profile.get("name", "")
                    self._server_name_text.value = name or t("server_list.no_server")
                    _, loc_str = self._extract_location_details(profile)
                    self._server_flag_text.visible = False
                    self._server_location_text.value = loc_str
                    self._server_location_text.visible = bool(loc_str)
        except Exception:
            pass

    @staticmethod
    def _get_flag_emoji(country_code: Optional[str]) -> str:
        """Convert ISO-2 country code to unicode flag emoji (e.g. 'FI' -> '🇫🇮')."""
        if not country_code or len(country_code) != 2:
            return "🌐"
        try:
            return "".join(chr(127397 + ord(c.upper())) for c in country_code)
        except Exception:
            return "🌐"

    def dispose(self) -> None:
        """Release EventBus subscriptions held by this view."""
        event_bus.unsubscribe(TOPIC_TELEMETRY_UPDATED, self._on_telemetry_event)
        event_bus.unsubscribe(TOPIC_CONNECTION_STATE_CHANGED, self._on_connection_state_event)
        event_bus.unsubscribe(TOPIC_ACTIVE_SERVER_PING_UPDATED, self._on_active_server_ping_updated)
        event_bus.unsubscribe(TOPIC_SERVER_INSPECTED, self._on_server_inspected)
        # WaveVisualizer has no owned resources; nothing to dispose.

    def _on_controller_state_changed(self, state: DashboardState, label: str) -> None:
        """Handle state change notification from DashboardController."""
        self._is_connected = state == DashboardState.CONNECTED
        self._is_connecting = state == DashboardState.CONNECTING
        self._is_disconnecting = state == DashboardState.DISCONNECTING

        if state == DashboardState.CONNECTING:
            self._toggle_button.set_connecting(label)
        elif state == DashboardState.CONNECTED:
            self._toggle_button.set_connected(label)
        elif state == DashboardState.DISCONNECTING:
            self._toggle_button.set_disconnecting(label)
        else:
            self._toggle_button.set_disconnected(label)

    def _on_controller_stats_updated(self, dl_text: str, ul_text: str, total_bps: float) -> None:
        """Handle stats update from DashboardController."""
        self._traffic_cards.update_speeds(dl_text, ul_text)
        self._toggle_button.update_network_activity(total_bps)
        if self._wave_visualizer is not None:
            self._wave_visualizer.update_traffic(total_bps)

    def _on_telemetry_event(self, data) -> None:
        """Handle telemetry_updated EventBus events (published on the UI event loop)."""
        if not isinstance(data, dict):
            return
        try:
            self.update_network_stats(
                rate_str=data.get("rate_str", "0.0 MB/s"),
                download_bps=float(data.get("download_bps", 0.0)),
                upload_bps=float(data.get("upload_bps", 0.0)),
                total_bps=float(data.get("total_bps", 0.0)),
            )
        except Exception:
            pass

    def _on_active_server_ping_updated(self, data) -> None:
        """Handle active_server_ping_updated events and render latency live."""
        if not isinstance(data, dict):
            return
        # Only meaningful while disconnected — once connected the status text is
        # driven by the connection state machine.
        if self._is_connected or self._is_connecting or self._is_disconnecting:
            return
        result_str = data.get("result_str")
        if not result_str:
            return
        try:
            self._toggle_button.set_pre_connection_ping(result_str, bool(data.get("success", False)))
        except Exception:
            pass

    def _on_server_inspected(self, data) -> None:
        """Refresh dashboard server info when the selected/active server's
        inspection completes (a server that was never inspected now resolves a
        country/name after the first successful connect or selection)."""
        if not isinstance(data, dict):
            return
        server_id = data.get("server_id")
        if server_id is None:
            return
        try:
            app_ctx = self._app_context
            if app_ctx is None or not hasattr(app_ctx, "get_profile_by_id") or not hasattr(
                app_ctx, "settings"
            ):
                return
            # Only refresh for the server the user actually has selected, so a
            # background batch ping never clobbers the dashboard title. Works for
            # both the connected case and the just-selected (not yet connected)
            # case.
            try:
                selected_id = app_ctx.settings.get_last_selected_profile_id()
            except Exception:
                selected_id = None
            if selected_id is not None and str(selected_id) != str(server_id):
                return
            profile = app_ctx.get_profile_by_id(server_id)
            if not profile:
                return
            # Re-resolve (country/name may have just landed from the inspect).
            from src.ui.helpers.profile_presenter import ProfilePresenter

            info = ProfilePresenter.extract_profile_info(profile)
            self.update_server_info(
                name=profile.get("name") or profile.get("remark", ""),
                latency=info.get("latency", ""),
                protocol=info.get("protocol", ""),
                country_code=info.get("country_code", ""),
                country_name=info.get("country_name", ""),
                profile=profile,
            )
        except Exception:
            pass

    def _on_connection_state_event(self, data) -> None:
        """Handle connection_state_changed EventBus events in real time."""
        if isinstance(data, EngineEvent):
            data = data.to_dict()
        if not isinstance(data, dict):
            return
        page = self._safe_page()
        if page is not None:
            try:
                page.run_task(self._run_connection_event, data)
                return
            except Exception:
                pass
        self._apply_connection_event(data)

    def _safe_page(self):
        """Return the Flet page this control is mounted on, or None."""
        try:
            return self.page
        except Exception:
            return None

    async def _run_connection_event(self, data) -> None:
        """Async wrapper executed on the Flet event loop."""
        self._apply_connection_event(data)

    def _reset_traffic_metrics(self) -> None:
        """Reset speed metrics and wave visualizer in-place."""
        try:
            self._traffic_cards.update_speeds("0 B/s", "0 B/s")
            if self._wave_visualizer is not None:
                self._wave_visualizer.reset_heights()
        except Exception:
            pass

    def _apply_connection_event(self, data) -> None:
        try:
            evt = data.get("event")
            if evt is None:
                self._apply_fsm_state_event(data)
                return
            payload = data.get("data") or {}
            connected_at = payload.get("connected_at")
            if evt == "connected":
                self.set_connection_state(is_connected=True, connected_at=connected_at)
            elif evt == "connecting":
                self.set_connection_state(is_connected=False, is_connecting=True)
            elif evt == "disconnecting":
                self.set_connection_state(is_connected=False, is_disconnecting=True)
            elif evt in ("disconnected", "connect_failed"):
                self.set_connection_state(is_connected=False)
                self._reset_traffic_metrics()
        except Exception:
            pass

    def _apply_fsm_state_event(self, data) -> None:
        """React to raw ConnectionFSM transition payloads (no 'event' key)."""
        try:
            new_state = data.get("new_state") or data.get("state")
            if new_state in ("error", "disconnected", "stopping"):
                self.set_connection_state(is_connected=False)
                self._reset_traffic_metrics()
            elif new_state == "connected":
                self.set_connection_state(is_connected=True)
            elif new_state in ("starting", "preparing"):
                self.set_connection_state(is_connected=False, is_connecting=True)
            elif new_state == "stopping":
                self.set_connection_state(is_connected=False, is_disconnecting=True)
        except Exception:
            pass

    def set_connection_state(
        self,
        is_connected: bool,
        is_connecting: bool = False,
        is_disconnecting: bool = False,
        connected_at: Optional[float] = None,
    ) -> None:
        """Update dashboard connection state (mirrors the legacy DashboardView API)."""
        self._is_connected = is_connected
        self._is_connecting = is_connecting
        self._is_disconnecting = is_disconnecting
        self._controller.set_connection_state(
            is_connected=is_connected,
            is_connecting=is_connecting,
            is_disconnecting=is_disconnecting,
            connected_at=connected_at,
        )

    def set_step(self, step_text: str) -> None:
        """Update the center status text during connection step transitions."""
        if not step_text:
            return
        self._toggle_button.set_step(get_short_status_label(step_text))

    def set_pre_connection_ping(self, latency_text: str, is_success: bool = True) -> None:
        """Update active server ping on controller and connection button when disconnected."""
        label = self._controller.update_ping(latency_text, is_success)
        if label and not self._is_connected and not self._is_connecting and not self._is_disconnecting:
            self._toggle_button.set_disconnected(label)

    def set_state_disconnected(self) -> None:
        """Update UI to disconnected state."""
        self.set_connection_state(is_connected=False)

    def set_state_connecting(self) -> None:
        """Update UI to connecting state."""
        self.set_connection_state(is_connected=False, is_connecting=True)

    def set_state_connected(self) -> None:
        """Update UI to connected state."""
        self.set_connection_state(is_connected=True)

    def set_state_disconnecting(self) -> None:
        """Update UI to disconnecting state."""
        self.set_connection_state(is_connected=False, is_disconnecting=True)

    def update_uptime(self, elapsed: int | str) -> None:
        """Update uptime counter."""
        page = self._safe_page()
        if page is not None:
            try:
                page.run_task(self._run_uptime_update, elapsed)
                return
            except Exception:
                pass
        self._apply_uptime_update(elapsed)

    async def _run_uptime_update(self, elapsed: int | str) -> None:
        """Async wrapper executed on the Flet event loop."""
        self._apply_uptime_update(elapsed)

    def _apply_uptime_update(self, elapsed: int | str) -> None:
        self._toggle_button.update_uptime(elapsed)

    def update_glow_intensity(self, total_bps: float = 0.0) -> None:
        """Update live throughput glow on the connection button."""
        self._toggle_button.update_network_activity(total_bps)

    def update_network_stats(
        self,
        rate_str: str = "0.0 MB/s",
        upload_str: str = "0.0 MB",
        download_str: str = "0.0 MB",
        download_bps: float = 0.0,
        upload_bps: float = 0.0,
        total_bps: float = 0.0,
        speed_text: Optional[str] = None,
        upload_total: Optional[str] = None,
        download_total: Optional[str] = None,
    ) -> None:
        """Update download and upload throughput text values and wave visualizer."""
        self._controller.process_network_stats(
            rate_str=rate_str,
            upload_str=upload_str,
            download_str=download_str,
            download_bps=download_bps,
            upload_bps=upload_bps,
            total_bps=total_bps,
            speed_text=speed_text,
            upload_total=upload_total,
            download_total=download_total,
        )
        if self._wave_visualizer is not None:
            self._wave_visualizer.update_traffic(total_bps)

    def update_internet_status(self, is_online: bool) -> None:
        """Update internet status indicator."""
        self._is_online = is_online
        self._toggle_button.set_online_status(is_online)

    def update_server_info(
        self,
        name: str = "",
        latency: str = "",
        protocol: str = "",
        encryption: str = "",
        server_ip: str = "",
        country_code: str = "",
        country_name: str = "",
        **kwargs,
    ) -> None:
        """Update active server title and flag/location subtitle."""
        profile = kwargs.get("profile")
        if isinstance(profile, dict):
            name = name or profile.get("name", "")
            country_code = country_code or profile.get("country_code", "")
            country_name = country_name or profile.get("country_name", "")
        else:
            profile = {}

        if name:
            self._server_name_text.value = name
        else:
            self._server_name_text.value = t("server_list.no_server")

        _, loc_str = self._extract_location_details(profile, country_code, country_name)
        self._server_flag_text.visible = False
        self._server_location_text.value = loc_str
        self._server_location_text.visible = bool(loc_str)

        try:
            if self._server_info_container.page:
                self._server_info_container.update()
        except Exception:
            pass

        # Also refresh the page-level control so the change reaches the render
        # even if the info container's own .page accessor was unavailable.
        try:
            if self.page is not None:
                self.update()
        except Exception:
            pass

        if self._server_card_component and hasattr(self._server_card_component, "update_server"):
            if profile:
                try:
                    self._server_card_component.update_server(profile)
                except Exception:
                    pass

    def update_lan_sharing(self, is_enabled: bool, ip_address: str = "") -> None:
        """Update LAN sharing status indicator."""
        self._lan_sharing_enabled = is_enabled

    def set_lan_sharing_state(self, enabled: bool) -> None:
        """Update LAN sharing status indicator."""
        self._lan_sharing_enabled = enabled


# Backward-compatibility alias
DashboardView = DashboardPage
