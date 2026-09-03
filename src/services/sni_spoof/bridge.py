"""SNI-spoof lifecycle bridge — pure event-reactive, zero manual flags.

Single responsibility: translate EventBus events into start/stop/update calls
on the process-shared SniSpoofService.  No boolean flag is stored here; every
decision is derived from the canonical sources at call time:

  - Connection liveness  → connection_fsm.state  (singleton FSM, thread-safe)
  - SNI enabled/disabled → SettingsRepository     (read on demand, fail-safe)

Policy:
  SNI_SPOOF_CHANGED (enabled_changed=True, enabled=True):
    Read FSM state. If CONNECTED → start(enable_pid_watcher=True).
    Otherwise → start(enable_pid_watcher=False)  [standby for ping probes].
  SNI_SPOOF_CHANGED (enabled_changed=True, enabled=False):
    stop() unconditionally.
  SNI_SPOOF_CHANGED (config field edit, no enabled_changed marker):
    Call update_target() when CONNECT_IP/PORT changed — hot-swap without
    closing the local socket.
  CONNECTION_STATE_CHANGED → connected:
    start(enable_pid_watcher=True)  [promote standby, or start fresh].
  CONNECTION_STATE_CHANGED → disconnected / stopping / error:
    If SNI still enabled → start(enable_pid_watcher=False)  [demote to standby].
    Else → stop().
"""

import threading

import loguru

from src.core.event_bus import TOPIC_CONNECTION_STATE_CHANGED, TOPIC_SNI_SPOOF_CHANGED, event_bus
from src.core.fsm.connection_fsm import ConnectionState, connection_fsm
from src.services.sni_spoof.sni_spoof_service import get_sni_spoof_service

logger = loguru.logger

_BRIDGE_LOCK = threading.Lock()
_bridge_installed = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_connection_state(data) -> str | None:
    """Read the connection state from an EngineEvent or a plain dict."""
    payload = getattr(data, "payload", None)
    if isinstance(payload, dict):
        return payload.get("state")
    if isinstance(data, dict):
        return data.get("state")
    return None


def _sni_spoof_is_enabled() -> bool:
    """Read current SNI-spoof enabled flag from settings (fail-safe)."""
    try:
        from src.core.constants import CONFIG_DIR
        from src.repositories.settings_repository import SettingsRepository

        return SettingsRepository(CONFIG_DIR).get_sni_spoof_enabled()
    except Exception:
        return False


def _is_connected() -> bool:
    """Return True iff the FSM is currently in CONNECTED state."""
    return connection_fsm.state == ConnectionState.CONNECTED


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def _on_connection_state_changed(data) -> None:
    """React to connection lifecycle events — derive all decisions from FSM state."""
    state = _extract_connection_state(data)
    if state is None:
        return

    if state == ConnectionState.CONNECTED.value:
        # VPN tunnel is live — promote standby listener (or start fresh) with
        # the PID watcher so Xray death auto-stops the relay.
        if not _sni_spoof_is_enabled():
            return
        try:
            get_sni_spoof_service().start(enable_pid_watcher=True)
        except Exception:
            logger.debug("[SniSpoof] start on connect failed")

    elif state in (
        ConnectionState.DISCONNECTED.value,
        ConnectionState.STOPPING.value,
        ConnectionState.ERROR.value,
    ):
        service = get_sni_spoof_service()
        if _sni_spoof_is_enabled():
            try:
                # Demote: detach PID watcher, keep port bound for ping probes.
                service.start(enable_pid_watcher=False)
            except Exception:
                logger.debug("[SniSpoof] demote to standby on disconnect failed")
        else:
            try:
                service.stop()
            except Exception:
                logger.debug("[SniSpoof] stop on disconnect failed")


def _on_sni_spoof_changed(data) -> None:
    """React to UI toggle and config-field edits.

    Genuine master-switch toggle (``enabled_changed=True``):
      → start with pid_watcher matching current FSM state, or stop.

    Config-field edit (no ``enabled_changed`` marker):
      → hot-update target if CONNECT_IP/PORT changed.
    """
    if not isinstance(data, dict):
        return

    if data.get("enabled_changed") is True:
        enabled = bool(data.get("enabled"))
        service = get_sni_spoof_service()
        if enabled:
            # Use FSM to decide whether a PID watcher is appropriate right now.
            pid_watch = _is_connected()
            if not service.running:
                service.start(enable_pid_watcher=pid_watch)
            else:
                service._adjust_pid_watcher(pid_watch)
        else:
            service.stop()
        return

    # Config-field edit — hot-swap target if relay is running.
    connect_ip = data.get("CONNECT_IP") or data.get("connect_ip")
    connect_port = data.get("CONNECT_PORT") or data.get("connect_port")
    if connect_ip or connect_port:
        service = get_sni_spoof_service()
        if service.running:
            try:
                import src.services.sni_spoof.listener as _lmod

                new_ip = connect_ip or _lmod.CONNECT_IP
                new_port = int(connect_port or _lmod.CONNECT_PORT)
                service.update_target(new_ip, new_port)
            except Exception as e:
                logger.debug(f"[SniSpoof] hot-swap target failed: {e}")


# ---------------------------------------------------------------------------
# Bridge installation
# ---------------------------------------------------------------------------


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
    """Test hook: unhook the bridge and clear tracked state."""
    global _bridge_installed
    with _BRIDGE_LOCK:
        _bridge_installed = False
    event_bus.unsubscribe(TOPIC_SNI_SPOOF_CHANGED, _on_sni_spoof_changed)
    event_bus.unsubscribe(TOPIC_CONNECTION_STATE_CHANGED, _on_connection_state_changed)
