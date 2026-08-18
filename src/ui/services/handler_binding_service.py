"""Handler Binding Service - initializes and configures post-UI build event handlers and background tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.event_bus import (
    EVENT_CORE_CRASHED,
    TOPIC_CONNECTION_STATE_CHANGED,
    TOPIC_LAN_SHARING_CHANGED,
    TOPIC_SNI_SPOOF_CHANGED,
    event_bus,
)

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


class HandlerBindingService:
    """Service encapsulating post-UI build handler binding logic."""

    def __init__(self, main_window: MainWindow) -> None:
        self._mw = main_window

    def bind_handlers(self) -> None:
        """Bind all post-UI build handlers and start event listeners."""
        mw = self._mw

        mw._connection_handler.setup(
            ui_helper=mw._ui_helper,
            connection_button=mw._connection_button,
            status_display=mw._status_display,
            log_viewer=mw._log_viewer,
            toast=mw._toast,
            systray=mw._systray,
            logs_drawer_component=mw._logs_drawer_component,
            latency_monitor_handler=mw._latency_monitor_handler,
            is_running_getter=lambda: mw._is_running,
            is_running_setter=mw._set_is_running,
            connecting_getter=lambda: mw._connecting,
            connecting_setter=mw._set_connecting,
            selected_profile_getter=lambda: mw._selected_profile,
            current_mode_getter=lambda: mw._current_mode,
            update_horizon_glow_callback=mw._update_horizon_glow,
            profile_manager_is_running_setter=mw._set_profile_manager_running,
            monitoring_service_is_running_setter=mw._set_monitoring_service_running,
        )

        mw._connection_handler._lan_card_callback = lambda show: (
            mw._lan_sharing_card.set_visible(show) if mw._lan_sharing_card else None
        )

        mw._reconnect_event_handler.setup(
            ui_helper=mw._ui_helper,
            toast=mw._toast,
            status_display=mw._status_display,
            connection_button=mw._connection_button,
            systray=mw._systray,
            update_horizon_glow_callback=mw._update_horizon_glow,
            is_running_setter=mw._set_is_running,
            profile_manager_is_running_setter=mw._set_profile_manager_running,
            monitoring_service_is_running_setter=mw._set_monitoring_service_running,
            reset_ui_callback=mw._reset_ui_disconnected,
        )

        mw._theme_handler.setup(
            page=mw._page,
            connection_button=mw._connection_button,
            server_card=mw._server_card,
            header=mw._header,
        )

        mw._installer_handler.setup(page=mw._page, ui_helper=mw._ui_helper, toast=mw._toast)

        mw._latency_monitor_handler.setup(
            page=mw._page,
            status_display=mw._status_display,
            server_card=mw._server_card,
            server_list=mw._server_list,
            ui_helper=mw._ui_helper,
            is_running_getter=lambda: mw._is_running,
            connecting_getter=lambda: mw._connecting,
            selected_profile_getter=lambda: mw._selected_profile,
            connection_button=mw._connection_button,
        )

        mw._network_stats_handler.setup(
            page=mw._page,
            status_display=mw._status_display,
            connection_button=mw._connection_button,
            logs_drawer_component=mw._logs_drawer_component,
            earth_glow=mw._earth_glow,
            logs_heartbeat=mw._logs_heartbeat,
            heartbeat=mw._heartbeat,
            is_running_getter=lambda: mw._is_running,
            active_tab_getter=lambda: mw._active_tab,
        )

        mw._background_task_handler.setup(page=mw._page)
        mw._systray.setup(mw)
        mw._background_task_handler.start()

        event_bus.subscribe("profile_selected", mw._update_selected_profile_ui)
        event_bus.subscribe(
            TOPIC_CONNECTION_STATE_CHANGED,
            # EventBus handlers run on the publisher's thread (background
            # connect/disconnect workers), so marshal the UI-sync onto the Flet
            # event loop instead of mutating controls from a foreign thread.
            lambda _: mw._ui_helper.call(mw._sync_dashboard_connection_state),
        )
        # Core-process crash (sing-box/Xray-core died unexpectedly): reset the UI
        # back to DISCONNECTED and surface the Persian error toast.
        event_bus.subscribe(EVENT_CORE_CRASHED, mw._on_core_crashed)
        event_bus.subscribe(
            TOPIC_LAN_SHARING_CHANGED,
            lambda d: (mw._nav_sidebar.update_lan_button(d.get("enabled", False)) if mw._nav_sidebar else None),
        )
        event_bus.subscribe(
            "lan_toggled",
            lambda d: (mw._nav_sidebar.update_lan_button(d.get("allow_lan", False)) if mw._nav_sidebar else None),
        )
        event_bus.subscribe(
            TOPIC_SNI_SPOOF_CHANGED,
            lambda d: (
                mw._nav_sidebar.update_sni_spoof_button(d.get("enabled", False))
                if mw._nav_sidebar and isinstance(d, dict) and "enabled" in d
                else None
            ),
        )

        mw._stats_forwarding.start()
