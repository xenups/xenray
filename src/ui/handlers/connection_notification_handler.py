"""Connection Notification Handler - Manages desktop notifications for VPN connection lifecycle.

Deterministic state tracking prevents duplicate notifications, ensures only genuine
state transitions are reported, distinguishes intentional manual disconnections from
unexpected drops/crashes, and confirms actual tunnel establishment before notifying.
"""

from __future__ import annotations

import threading
from enum import Enum, auto
from typing import Callable, Optional

from src.core.event_bus import EVENT_CORE_CRASHED, TOPIC_CONNECTION_STATE_CHANGED, EngineEvent
from src.core.event_bus import event_bus as default_event_bus
from src.core.i18n import t
from src.core.logger import logger


class NotificationConnectionState(Enum):
    """Deterministic connection notification states."""

    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()


class ConnectionNotificationHandler:
    """Manages reliable desktop notifications for VPN connection state changes.

    Responsibilities:
    - Emit a desktop notification upon genuine, confirmed connection success.
    - Include the active profile name in success notifications when available.
    - Emit a notification upon intentional manual disconnection.
    - Emit a warning notification when an established connection drops unexpectedly
      (e.g., core crash, tunnel loss, failed auto-reconnect).
    - Prevent duplicate notifications caused by polling, retries, repeated callbacks,
      or duplicate status events.
    - Suppress disconnection notifications if the VPN was never successfully connected.
    - Handle application shutdown gracefully without spurious notifications.
    """

    def __init__(
        self,
        systray=None,
        selected_profile_getter: Optional[Callable[[], Optional[dict]]] = None,
        notify_fn: Optional[Callable[[str, str], None]] = None,
        bus=None,
    ) -> None:
        self._lock = threading.Lock()
        self._systray = systray
        self._selected_profile_getter = selected_profile_getter
        self._notify_fn = notify_fn
        self._bus = bus or default_event_bus

        self._state = NotificationConnectionState.DISCONNECTED
        self._was_connected = False
        self._is_manual_disconnect = False
        self._is_shutting_down = False
        self._active_profile_name: Optional[str] = None
        self._subscribed = False

    def setup(
        self,
        systray=None,
        selected_profile_getter: Optional[Callable[[], Optional[dict]]] = None,
        notify_fn: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """Bind or update UI and systray dependencies."""
        with self._lock:
            if systray is not None:
                self._systray = systray
            if selected_profile_getter is not None:
                self._selected_profile_getter = selected_profile_getter
            if notify_fn is not None:
                self._notify_fn = notify_fn

    def start(self) -> None:
        """Subscribe to connection lifecycle topics on EventBus."""
        with self._lock:
            if self._subscribed:
                return
            self._bus.subscribe(TOPIC_CONNECTION_STATE_CHANGED, self._on_connection_state_event)
            self._bus.subscribe(EVENT_CORE_CRASHED, self._on_core_crashed)
            self._subscribed = True
            logger.debug("[ConnectionNotificationHandler] Subscribed to connection events")

    def cleanup(self) -> None:
        """Unsubscribe from EventBus topics."""
        with self._lock:
            if not self._subscribed:
                return
            try:
                self._bus.unsubscribe(TOPIC_CONNECTION_STATE_CHANGED, self._on_connection_state_event)
                self._bus.unsubscribe(EVENT_CORE_CRASHED, self._on_core_crashed)
            except Exception as e:
                logger.debug(f"[ConnectionNotificationHandler] Error during cleanup: {e}")
            self._subscribed = False

    def set_shutting_down(self, shutting_down: bool = True) -> None:
        """Set application shutdown state to suppress spurious notifications."""
        with self._lock:
            self._is_shutting_down = shutting_down

    def mark_manual_disconnect(self) -> None:
        """Mark that a pending disconnect was explicitly initiated by the user."""
        with self._lock:
            self._is_manual_disconnect = True

    def reset(self) -> None:
        """Reset internal notification state."""
        with self._lock:
            self._state = NotificationConnectionState.DISCONNECTED
            self._was_connected = False
            self._is_manual_disconnect = False
            self._active_profile_name = None

    # -------------------------------------------------------------------------
    # Notification Actions
    # -------------------------------------------------------------------------

    def handle_connecting(self) -> None:
        """Handle connecting state (transition only, no notification)."""
        with self._lock:
            # Do not show success merely because connection started
            self._state = NotificationConnectionState.CONNECTING

    def handle_connected(self, profile_name: Optional[str] = None) -> bool:
        """Handle confirmed successful connection.

        Args:
            profile_name: Optional name of the connected profile/server.

        Returns:
            True if a notification was dispatched, False if duplicate/skipped.
        """
        with self._lock:
            if self._state == NotificationConnectionState.CONNECTED:
                # Deduplication: already in connected state
                return False

            self._state = NotificationConnectionState.CONNECTED
            self._was_connected = True
            self._is_manual_disconnect = False

            if not profile_name and self._selected_profile_getter:
                try:
                    profile = self._selected_profile_getter()
                    if profile and isinstance(profile, dict):
                        profile_name = profile.get("name")
                except Exception as e:
                    logger.debug(f"[ConnectionNotificationHandler] Could not resolve profile name: {e}")

            self._active_profile_name = profile_name

            if profile_name:
                message = t("notifications.connected_to", server=profile_name, default=f"Connected: {profile_name}")
            else:
                message = t("notifications.connected", default="Connected")

        self._send_notification(message, title="XenRay")
        return True

    def handle_connect_failed(self, reason: Optional[str] = None) -> bool:
        """Handle failed connection attempt (no false success notification)."""
        with self._lock:
            self._state = NotificationConnectionState.DISCONNECTED
            # Do not notify about disconnection if VPN was never connected
            self._was_connected = False
            self._is_manual_disconnect = False
            return False

    def handle_disconnecting(self, is_manual: bool = True) -> bool:
        """Handle transition to disconnecting."""
        with self._lock:
            if is_manual:
                self._is_manual_disconnect = True
            return True

    def handle_disconnected(self, is_manual: Optional[bool] = None, reason: Optional[str] = None) -> bool:
        """Handle disconnection completion.

        Args:
            is_manual: Explicit flag whether disconnect was manual. If None,
                uses the tracked `_is_manual_disconnect` state.
            reason: Optional reason string (e.g., 'core_crashed').

        Returns:
            True if a notification was dispatched, False otherwise.
        """
        with self._lock:
            if self._is_shutting_down:
                self._state = NotificationConnectionState.DISCONNECTED
                self._was_connected = False
                self._is_manual_disconnect = False
                return False

            # If never successfully connected, do not notify about disconnection
            if not self._was_connected and self._state != NotificationConnectionState.CONNECTED:
                self._state = NotificationConnectionState.DISCONNECTED
                self._is_manual_disconnect = False
                return False

            # If already disconnected, avoid duplicates
            if self._state == NotificationConnectionState.DISCONNECTED:
                return False

            manual = is_manual if is_manual is not None else (self._is_manual_disconnect and reason != "core_crashed")

            self._state = NotificationConnectionState.DISCONNECTED
            self._was_connected = False
            self._is_manual_disconnect = False
            self._active_profile_name = None

            if manual:
                message = t("notifications.disconnected", default="Disconnected")
            else:
                message = t("notifications.unexpected_disconnect", default="VPN connection lost unexpectedly")

        self._send_notification(message, title="XenRay")
        return True

    def handle_unexpected_disconnect(self, reason: Optional[str] = None) -> bool:
        """Handle unexpected connection loss (core crash, tunnel failure, etc.).

        Returns:
            True if a notification was dispatched, False otherwise.
        """
        with self._lock:
            if self._is_shutting_down:
                return False

            if not self._was_connected and self._state != NotificationConnectionState.CONNECTED:
                return False

            if self._state == NotificationConnectionState.DISCONNECTED:
                return False

            self._state = NotificationConnectionState.DISCONNECTED
            self._was_connected = False
            self._is_manual_disconnect = False
            self._active_profile_name = None

            message = t("notifications.unexpected_disconnect", default="VPN connection lost unexpectedly")

        self._send_notification(message, title="XenRay")
        return True

    # -------------------------------------------------------------------------
    # EventBus Handlers
    # -------------------------------------------------------------------------

    def _on_connection_state_event(self, event) -> None:
        """Handle connection_state_changed EventBus event."""
        if isinstance(event, EngineEvent):
            event_name = event.event_name
            payload = event.payload or {}
        elif isinstance(event, dict):
            event_name = event.get("event_name") or event.get("event") or event.get("payload", {}).get("event")
            payload = event.get("payload") if "payload" in event else event
        else:
            return

        if not isinstance(payload, dict):
            payload = {}

        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload

        if event_name == "connecting":
            self.handle_connecting()
        elif event_name in ("connected", "reconnected"):
            profile_name = data.get("profile_name")
            self.handle_connected(profile_name=profile_name)
        elif event_name == "connect_failed":
            self.handle_connect_failed(reason=data.get("reason"))
        elif event_name == "disconnecting":
            self.handle_disconnecting(is_manual=True)
        elif event_name == "disconnected":
            reason = data.get("reason")
            is_manual = False if reason == "core_crashed" else None
            self.handle_disconnected(is_manual=is_manual, reason=reason)
        elif event_name == "reconnect_failed":
            # Reconnect attempt after a drop failed completely
            self.handle_unexpected_disconnect(reason=data.get("reason") or "reconnect_failed")

    def _on_core_crashed(self, payload=None) -> None:
        """Handle EVENT_CORE_CRASHED event from CoreHealthMonitor."""
        self.handle_unexpected_disconnect(reason="core_crashed")

    # -------------------------------------------------------------------------
    # Fail-soft OS Notification Dispatch
    # -------------------------------------------------------------------------

    def _send_notification(self, message: str, title: str = "XenRay") -> None:
        """Dispatch desktop notification through systray or custom notify_fn (fail-soft)."""
        logger.info(f"[ConnectionNotificationHandler] Notification: title='{title}', message='{message}'")
        try:
            if self._notify_fn:
                self._notify_fn(message, title)
                return

            systray = self._systray
            if systray:
                notify = getattr(systray, "notify", None)
                if notify and callable(notify):
                    try:
                        # Call with title if supported, otherwise fallback to message only
                        import inspect

                        sig = inspect.signature(notify)
                        if len(sig.parameters) >= 2:
                            notify(message, title)
                        else:
                            notify(message)
                    except TypeError:
                        notify(message)
        except Exception as e:
            logger.warning(f"[ConnectionNotificationHandler] Notification failed: {e}")
