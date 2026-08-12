"""
Monitor Signals - Facts emitted by monitoring components.

Monitors emit signals (facts about what happened).
ConnectionManager converts signals to user-visible events.

This separation ensures:
- Monitors are reusable and testable
- Single source of truth for event policy
- No late events after disconnect
- No reconnect logic in monitors
"""

from enum import Enum, auto
from typing import Optional

from src.core.constants import CORE_SINGBOX, CORE_XRAY  # noqa: F401  (re-exported for callers)


class MonitorSignal(Enum):
    """
    Signals emitted by monitoring components.

    These are FACTS, not events. They carry no policy or UI semantics.
    ConnectionManager decides what to do with each signal.

    The payload dict passed alongside a signal is a plain fact container:
    ``{"source": CORE_XRAY | CORE_SINGBOX, ...}``.
    """

    # Passive log monitor detected a failure pattern in one of the core logs
    # (Xray-core or sing-box TUN engine)
    PASSIVE_FAILURE = auto()

    # Active monitor detected connectivity loss (probe-based, real connectivity)
    ACTIVE_LOST = auto()

    # Active monitor detected connectivity restored
    ACTIVE_RESTORED = auto()

    # Active monitor detected degraded connection (soft warning)
    ACTIVE_DEGRADED = auto()

    # A core engine process (Xray or sing-box) crashed / exited unexpectedly
    ENGINE_CRASHED = auto()


def signal_payload(source: str, **extra) -> dict:
    """Build a standard signal payload dict with the emitting core source."""
    payload = {"source": source}
    payload.update(extra)
    return payload
