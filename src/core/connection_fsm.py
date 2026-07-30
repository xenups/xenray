"""Finite State Machine (FSM) for managing application connection lifecycle states."""

from __future__ import annotations

import threading
from enum import Enum, auto
from typing import Callable, List

from src.core.logger import logger


class ConnectionState(Enum):
    """Explicit connection lifecycle states."""

    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()
    ERROR = auto()


class ConnectionFSM:
    """Thread-safe Finite State Machine for connection lifecycle management."""

    def __init__(self, initial_state: ConnectionState = ConnectionState.DISCONNECTED):
        self._state = initial_state
        self._lock = threading.Lock()
        self._listeners: List[Callable[[ConnectionState, ConnectionState], None]] = []

    @property
    def state(self) -> ConnectionState:
        """Get current connection state atomically."""
        with self._lock:
            return self._state

    def is_state(self, *states: ConnectionState) -> bool:
        """Check if current state matches any of the provided states."""
        with self._lock:
            return self._state in states

    def can_transition_to(self, target_state: ConnectionState) -> bool:
        """Check if transition to target_state is valid from current state."""
        with self._lock:
            current = self._state
            if target_state == ConnectionState.CONNECTING:
                return current in (ConnectionState.DISCONNECTED, ConnectionState.ERROR)
            elif target_state == ConnectionState.CONNECTED:
                return current == ConnectionState.CONNECTING
            elif target_state == ConnectionState.DISCONNECTING:
                return current in (ConnectionState.CONNECTED, ConnectionState.CONNECTING)
            elif target_state in (ConnectionState.DISCONNECTED, ConnectionState.ERROR):
                return True
            return False

    def transition_to(self, target_state: ConnectionState) -> bool:
        """Atomically transition to target_state if valid."""
        with self._lock:
            current = self._state

            if current == target_state:
                logger.debug(f"[ConnectionFSM] Transition ignored (already in {current.name})")
                return False

            allowed = False
            if target_state == ConnectionState.CONNECTING:
                allowed = current in (ConnectionState.DISCONNECTED, ConnectionState.ERROR)
            elif target_state == ConnectionState.CONNECTED:
                allowed = current == ConnectionState.CONNECTING
            elif target_state == ConnectionState.DISCONNECTING:
                allowed = current in (ConnectionState.CONNECTED, ConnectionState.CONNECTING)
            elif target_state in (ConnectionState.DISCONNECTED, ConnectionState.ERROR):
                allowed = True

            if not allowed:
                logger.warning(
                    f"[ConnectionFSM] Transition rejected: {current.name} -> {target_state.name}"
                )
                return False

            self._state = target_state
            logger.info(f"[ConnectionFSM] Transition: {current.name} -> {target_state.name}")
            listeners = list(self._listeners)

        for listener in listeners:
            try:
                listener(current, target_state)
            except Exception as e:
                logger.error(f"[ConnectionFSM] Listener error: {e}")

        return True

    def force_state(self, target_state: ConnectionState):
        """Force state transition for emergency cleanup or resets."""
        with self._lock:
            current = self._state
            self._state = target_state
            logger.info(f"[ConnectionFSM] Forced state: {current.name} -> {target_state.name}")
            listeners = list(self._listeners)

        for listener in listeners:
            try:
                listener(current, target_state)
            except Exception as e:
                logger.error(f"[ConnectionFSM] Listener error: {e}")

    def add_listener(self, listener: Callable[[ConnectionState, ConnectionState], None]):
        """Add callback for state transitions."""
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)
