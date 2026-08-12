"""Centralized Event-Driven Finite State Machine (ConnectionFSM).

Manages deterministic connection states, transition rules, and emits reactive state change events
over EventBus for UI and service subscribers.
"""

from __future__ import annotations

import threading
from enum import Enum
from typing import Any, Optional

from src.core.event_bus import TOPIC_CONNECTION_STATE_CHANGED, TOPIC_FSM_STATE_CHANGED, EventBus
from src.core.event_bus import event_bus as default_event_bus
from src.core.logger import logger


class ConnectionState(str, Enum):
    """Deterministic Connection Lifecycle States."""

    DISCONNECTED = "disconnected"
    PINGING = "pinging"  # pre-connection latency check (neon sweep) in progress
    STARTING = "starting"
    PREPARING = "preparing"
    CONNECTED = "connected"
    STOPPING = "stopping"
    ERROR = "error"


class ConnectionFSM:
    """Thread-safe Finite State Machine for connection lifecycle management."""

    # Strict transition rules mapping current_state -> set of valid next states.
    ALLOWED_TRANSITIONS: dict[ConnectionState, set[ConnectionState]] = {
        ConnectionState.DISCONNECTED: {
            ConnectionState.PINGING,
            ConnectionState.STARTING,
            ConnectionState.PREPARING,  # engine "connecting" enters PREPARING directly
            ConnectionState.STOPPING,  # engine emits disconnecting->disconnected even when idle
            ConnectionState.ERROR,
        },
        ConnectionState.PINGING: {
            ConnectionState.STARTING,  # user clicked Connect during the ping check
            ConnectionState.DISCONNECTED,  # ping completed without a click (idle)
            ConnectionState.STOPPING,  # defensive stop during the ping check
            ConnectionState.ERROR,
        },
        ConnectionState.STARTING: {
            ConnectionState.PREPARING,
            ConnectionState.STOPPING,
            ConnectionState.ERROR,
            ConnectionState.DISCONNECTED,
        },
        ConnectionState.PREPARING: {
            ConnectionState.CONNECTED,
            ConnectionState.STOPPING,
            ConnectionState.ERROR,
            ConnectionState.DISCONNECTED,
        },
        ConnectionState.CONNECTED: {
            ConnectionState.STOPPING,
            ConnectionState.ERROR,
            ConnectionState.DISCONNECTED,
        },
        ConnectionState.STOPPING: {
            ConnectionState.DISCONNECTED,
            ConnectionState.ERROR,
        },
        ConnectionState.ERROR: {
            ConnectionState.DISCONNECTED,
            ConnectionState.STARTING,
        },
    }

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._bus = bus or default_event_bus
        self._state = ConnectionState.DISCONNECTED
        self._lock = threading.Lock()
        self._state_generation = 0

    @property
    def state(self) -> ConnectionState:
        """Get current FSM state (thread-safe)."""
        with self._lock:
            return self._state

    @property
    def state_generation(self) -> int:
        """Get current state generation counter for cancellation tokens."""
        with self._lock:
            return self._state_generation

    @property
    def is_connected(self) -> bool:
        """Check if currently in CONNECTED state."""
        return self.state == ConnectionState.CONNECTED

    @property
    def is_busy(self) -> bool:
        """Check if currently transitioning (STARTING, PREPARING, or STOPPING)."""
        return self.state in {
            ConnectionState.STARTING,
            ConnectionState.PREPARING,
            ConnectionState.STOPPING,
        }

    def transition_to(
        self,
        new_state: ConnectionState | str,
        payload: Any = None,
        force: bool = False,
    ) -> bool:
        """
        Transition FSM to new state if valid.

        Args:
            new_state: Target ConnectionState or matching string name.
            payload: Optional data passed to subscribers.
            force: If True, bypass transition validation (emergency reset/error recovery).

        Returns:
            True if transition succeeded, False if blocked/invalid.
        """
        if isinstance(new_state, str):
            try:
                new_state = ConnectionState(new_state.lower())
            except ValueError:
                logger.error(f"[ConnectionFSM] Unknown state string: '{new_state}'")
                return False

        with self._lock:
            old_state = self._state
            if old_state == new_state and not force:
                logger.debug(f"[ConnectionFSM] Already in state {new_state}, skipping transition.")
                return True

            allowed = self.ALLOWED_TRANSITIONS.get(old_state, set())
            if not force and new_state not in allowed:
                logger.warning(
                    f"[ConnectionFSM] Invalid state transition from '{old_state.value}' to '{new_state.value}'. Transition blocked."
                )
                return False

            self._state = new_state
            self._state_generation += 1
            current_gen = self._state_generation

        logger.info(
            f"[FSM] Transitioning: {old_state.value} -> {new_state.value} (Gen: {current_gen} | Trigger: {payload})"
        )

        # Publish reactive events over EventBus
        event_payload = {
            "old_state": old_state.value,
            "new_state": new_state.value,
            "state": new_state.value,
            "generation": current_gen,
            "payload": payload,
        }

        self._bus.publish(TOPIC_CONNECTION_STATE_CHANGED, event_payload)
        self._bus.publish(TOPIC_FSM_STATE_CHANGED, event_payload)
        return True

    def reset(self, error: bool = False) -> None:
        """Force reset state to DISCONNECTED or ERROR."""
        target = ConnectionState.ERROR if error else ConnectionState.DISCONNECTED
        self.transition_to(target, force=True)


# Default singleton FSM instance
connection_fsm = ConnectionFSM()
