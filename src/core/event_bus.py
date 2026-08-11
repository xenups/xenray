"""Centralized Thread-Safe Event Bus for Decoupled Pub/Sub Event Messaging."""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List

from src.core.logger import logger

# Canonical event topic names shared across producers and subscribers.
TOPIC_CONNECTION_STATE_CHANGED = "connection_state_changed"
TOPIC_TELEMETRY_UPDATED = "telemetry_updated"
TOPIC_PROFILE_SELECTED = "profile_selected"
TOPIC_LAN_TOGGLED = "lan_toggled"
TOPIC_LAN_SHARING_CHANGED = "lan_sharing_changed"


class EventBus:
    """Thread-safe Pub/Sub Event Bus eliminating circular view/service dependencies."""

    _instance: EventBus | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}
        self._subscribers_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> EventBus:
        """Get or create singleton EventBus instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def subscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Subscribe a handler callback to a specific event topic."""
        with self._subscribers_lock:
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []
            if handler not in self._subscribers[event_name]:
                self._subscribers[event_name].append(handler)
                logger.debug(f"[EventBus] Subscribed handler to '{event_name}'")

    def unsubscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Unsubscribe a handler callback from an event topic."""
        with self._subscribers_lock:
            if event_name in self._subscribers and handler in self._subscribers[event_name]:
                self._subscribers[event_name].remove(handler)
                logger.debug(f"[EventBus] Unsubscribed handler from '{event_name}'")

    def publish(self, event_name: str, data: Any = None) -> None:
        """Publish event payload data to all subscribed handlers on topic."""
        with self._subscribers_lock:
            handlers = list(self._subscribers.get(event_name, []))

        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error(f"[EventBus] Error executing handler for event '{event_name}': {e}")

    def clear(self) -> None:
        """Clear all subscriptions (useful for test resets)."""
        with self._subscribers_lock:
            self._subscribers.clear()


# Global default instance helper
event_bus = EventBus.get_instance()
