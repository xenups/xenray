"""Reconnect Event Handler - Handles UI updates for passive reconnect events."""

from src.core.i18n import t
from src.core.logger import logger


class ReconnectEventHandler:
    """
    Handles UI updates for passive reconnect events.

    Subscribes to ConnectionManager events and updates UI components.
    Follows SRP by separating reconnect UI logic from connection lifecycle.
    """

    def __init__(self, connection_manager):
        """
        Initialize ReconnectEventHandler.

        Args:
            connection_manager: ConnectionManager instance to subscribe to events
        """
        self._connection_manager = connection_manager
        self._ui_helper = None
        self._toast = None
        self._status_display = None
        self._connection_button = None
        self._systray = None
        self._update_horizon_glow_callback = None

        # State setters
        self._is_running_setter = None
        self._profile_manager_is_running_setter = None
        self._monitoring_service_is_running_setter = None
        self._reset_ui_callback = None

    def setup(
        self,
        ui_helper,
        toast,
        status_display,
        connection_button,
        systray,
        update_horizon_glow_callback,
        is_running_setter,
        profile_manager_is_running_setter,
        monitoring_service_is_running_setter,
        reset_ui_callback,
    ):
        """Bind UI components and callbacks."""
        self._ui_helper = ui_helper
        self._toast = toast
        self._status_display = status_display
        self._connection_button = connection_button
        self._systray = systray
        self._update_horizon_glow_callback = update_horizon_glow_callback
        self._is_running_setter = is_running_setter
        self._profile_manager_is_running_setter = profile_manager_is_running_setter
        self._monitoring_service_is_running_setter = monitoring_service_is_running_setter
        self._reset_ui_callback = reset_ui_callback

        # Subscribe to events
        self._connection_manager.set_reconnect_event_listener(self._on_event)

    def cleanup(self):
        """Unsubscribe from events."""
        try:
            self._connection_manager.set_reconnect_event_listener(None)
            logger.debug("[ReconnectEventHandler] Cleaned up event listener")
        except Exception as e:
            logger.debug(f"[ReconnectEventHandler] Error during cleanup: {e}")

    def _on_event(self, event_type: str, data: dict):
        """Dispatch event to appropriate handler."""
        logger.debug(f"[ReconnectEventHandler] Event: {event_type}")

        handlers = {
            "failure_detected": self._handle_failure_detected,
            "connectivity_lost": self._handle_connectivity_lost,
            "connectivity_degraded": self._handle_connectivity_degraded,
            "connectivity_restored": self._handle_connectivity_restored,
            "reconnecting": self._handle_reconnecting,
            "reconnected": self._handle_reconnected,
            "reconnect_failed": self._handle_reconnect_failed,
        }

        handler = handlers.get(event_type)
        if handler:
            handler(data)

    def _ui_call(self, callback):
        """Safely execute UI callback."""
        if self._ui_helper and callback:
            self._ui_helper.call(callback)

    def _handle_failure_detected(self, data: dict):
        """Handle failure_detected event."""
        if self._toast:
            self._ui_call(lambda: self._toast.warning(t("connection.failure_detected"), 3000))
        if self._status_display:
            self._ui_call(lambda: self._status_display.set_step(t("connection.checking_network")))

    def _handle_connectivity_lost(self, data: dict):
        """Handle connectivity_lost event from ActiveConnectivityMonitor."""
        logger.info("[ReconnectEventHandler] Handling connectivity_lost event")
        if self._toast:
            self._ui_call(lambda: self._toast.warning(t("connection.failure_detected"), 3000))
        if self._status_display:
            self._ui_call(lambda: self._status_display.set_step(t("connection.checking_network")))

    def _handle_connectivity_degraded(self, data: dict):
        """Handle connectivity_degraded event - soft warning, connection may be unstable."""
        logger.info("[ReconnectEventHandler] Handling connectivity_degraded event")
        if self._status_display:
            self._ui_call(lambda: self._status_display.set_step(t("connection.checking_network")))

    def _handle_connectivity_restored(self, data: dict):
        """Handle connectivity_restored event from ActiveConnectivityMonitor."""
        logger.info("[ReconnectEventHandler] Handling connectivity_restored - updating UI to Connected")

        # Update state
        if self._is_running_setter:
            self._is_running_setter(True)
        if self._profile_manager_is_running_setter:
            self._profile_manager_is_running_setter(True)
        if self._monitoring_service_is_running_setter:
            self._monitoring_service_is_running_setter(True)

        # Update UI to Connected
        if self._connection_button:
            self._ui_call(self._connection_button.set_connected)
        if self._status_display:
            self._ui_call(self._status_display.set_connected)
        if self._update_horizon_glow_callback:
            self._ui_call(lambda: self._update_horizon_glow_callback("connected"))
        if self._toast:
            self._ui_call(lambda: self._toast.success(t("connection.reconnected"), 3000))
        if self._systray:
            self._systray.update_state()

    def _handle_reconnecting(self, data: dict):
        """Handle reconnecting event."""
        if self._connection_button:
            self._ui_call(self._connection_button.set_connecting)
        if self._status_display:
            self._ui_call(lambda: self._status_display.set_step(t("connection.reconnecting")))
        if self._update_horizon_glow_callback:
            self._ui_call(lambda: self._update_horizon_glow_callback("connecting"))

    def _handle_reconnected(self, data: dict):
        """Handle reconnected event."""
        logger.info("[ReconnectEventHandler] Handling reconnected event - updating UI")

        # Update state
        if self._is_running_setter:
            self._is_running_setter(True)
        if self._profile_manager_is_running_setter:
            self._profile_manager_is_running_setter(True)
        if self._monitoring_service_is_running_setter:
            self._monitoring_service_is_running_setter(True)

        # Update UI
        if self._connection_button:
            self._ui_call(self._connection_button.set_connected)
        if self._status_display:
            logger.debug("[ReconnectEventHandler] Calling status_display.set_connected()")
            self._ui_call(self._status_display.set_connected)
        if self._update_horizon_glow_callback:
            self._ui_call(lambda: self._update_horizon_glow_callback("connected"))
        if self._toast:
            self._ui_call(lambda: self._toast.success(t("connection.reconnected"), 3000))
        if self._systray:
            self._systray.update_state()

    def _handle_reconnect_failed(self, data: dict):
        """Handle reconnect_failed event."""
        reason = data.get("reason", "unknown")

        if self._toast:
            msg_key = "connection.no_internet" if reason == "no_internet" else "connection.reconnect_failed"
            self._ui_call(lambda: self._toast.error(t(msg_key), 3000))

        if self._reset_ui_callback:
            self._ui_call(self._reset_ui_callback)
