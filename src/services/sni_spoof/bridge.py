"""SNI-spoof lifecycle bridge — coordinates app events with the listener's lifecycle.

Single responsibility: translate UI toggle events and connection state changes
into start/stop calls on the process-shared SniSpoofService (nothing else lives
here). The service module owns the actual listener lifecycle; this module only
maps events to it.

Policy:
  - A master-switch toggle (``enabled_changed`` marker, emitted by the controller)
    starts the listener only while a connection is active, and stops it otherwise.
  - The listener must never keep relaying outside an active connection
    (VPN-leak guard), so a disconnect always stops it.
"""

import threading

import loguru

from src.core.event_bus import TOPIC_CONNECTION_STATE_CHANGED, TOPIC_SNI_SPOOF_CHANGED, event_bus
from src.services.sni_spoof.sni_spoof_service import get_sni_spoof_service

logger = loguru.logger

_BRIDGE_LOCK = threading.Lock()
_bridge_installed = False
_connection_active = False
_connection_lock = threading.Lock()


def _extract_connection_state(data) -> str | None:
    """Read the connection state from an EngineEvent or a plain dict."""
    payload = getattr(data, "payload", None)
    if isinstance(payload, dict):
        return payload.get("state")
    if isinstance(data, dict):
        return data.get("state")
    return None


def _on_connection_state_changed(data) -> None:
    """Track the connection state and stop the listener when the connection ends."""
    global _connection_active
    state = _extract_connection_state(data)
    if state is None:
        return
    active = state == "connected"
    with _connection_lock:
        _connection_active = active
    if not active:
        # Connection ended — the listener must not keep relaying outside the
        # tunnel (VPN-leak guard). Idempotent even though Xray also stops it.
        try:
            get_sni_spoof_service().stop()
        except Exception:
            logger.debug("[SniSpoof] stop on disconnect failed")


def _on_sni_spoof_changed(data) -> None:
    """React to UI toggle events: start only with an active connection, else stop.

    Only a genuine master-switch toggle (``enabled_changed`` marker set by the
    controller) drives start/stop. Plain config publishes (any field edit), which
    still carry ``enabled`` as a snapshot, must not stop an active listener.
    """
    if not isinstance(data, dict) or data.get("enabled_changed") is not True:
        return
    enabled = bool(data.get("enabled"))
    service = get_sni_spoof_service()
    if enabled:
        with _connection_lock:
            active = _connection_active
        if not active:
            logger.info("[SniSpoof] enabled with no active connection — will start on connect")
            return
        if not service.running:
            service.start()
    else:
        service.stop()


def install_sni_spoof_lifecycle_bridge() -> None:
    """Install the toggle<->service and connection-state subscriptions once."""
    global _bridge_installed
    with _BRIDGE_LOCK:
        if _bridge_installed:
            return
        _bridge_installed = True
    event_bus.subscribe(TOPIC_SNI_SPOOF_CHANGED, _on_sni_spoof_changed)
    event_bus.subscribe(TOPIC_CONNECTION_STATE_CHANGED, _on_connection_state_changed)
    logger.debug("[SniSpoof] lifecycle bridge installed")


def reset_sni_spoof_bridge_for_tests() -> None:
    """Test hook: unhook the bridge and clear tracked state (leaves the shared
    service alone — the service module owns that)."""
    global _bridge_installed, _connection_active
    with _BRIDGE_LOCK:
        _bridge_installed = False
        _connection_active = False
    event_bus.unsubscribe(TOPIC_SNI_SPOOF_CHANGED, _on_sni_spoof_changed)
    event_bus.unsubscribe(TOPIC_CONNECTION_STATE_CHANGED, _on_connection_state_changed)
