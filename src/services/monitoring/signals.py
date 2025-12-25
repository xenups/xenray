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


class MonitorSignal(Enum):
    """
    Signals emitted by monitoring components.

    These are FACTS, not events. They carry no policy or UI semantics.
    ConnectionManager decides what to do with each signal.
    """

    # Passive log monitor detected a failure pattern in logs
    PASSIVE_FAILURE = auto()

    # Active monitor detected connectivity loss (traffic stalled + error confirmed)
    ACTIVE_LOST = auto()

    # Active monitor detected connectivity restored
    ACTIVE_RESTORED = auto()

    # Active monitor detected degraded connection (soft warning)
    ACTIVE_DEGRADED = auto()
