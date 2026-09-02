"""Connection Manager - Facade for connection management with session-scoped lifecycle."""

import threading
import time
from typing import Optional

from loguru import logger

from src.core.app_context import AppContext
from src.core.connection_orchestrator import ConnectionOrchestrator
from src.core.constants import MODE_PROXY, MODE_VPN, OUTPUT_CONFIG_PATH, PROTOCOL_TUN
from src.core.i18n import t
from src.services.core_engines.singbox_service import SingboxService
from src.services.core_engines.xray_service import XrayService


class ConnectionManager:
    """
    Facade for VPN/Proxy connection management.

    Signal-Based Architecture:
    - Monitors emit SIGNALS (facts) - no event semantics
    - ConnectionManager is the SINGLE EVENT AUTHORITY
    - All signals are converted to events here
    - All late signals after disconnect are ignored here

    Session-Scoped Lifecycle:
    - Each connection has a unique session_id
    - Disconnect is TERMINAL: cancels all reconnect, monitoring, background tasks
    - No stale events can be emitted after disconnect

    State Machine: IDLE -> CONNECTING -> CONNECTED -> (RECONNECTING) -> DISCONNECTING -> IDLE
    """

    def __init__(self, app_context: AppContext):
        """Initialize ConnectionManager with injected dependencies (DIP)."""

        # Initialize services (Dependency Injection)
        from src.services.core_engines.legacy_config_service import LegacyConfigService
        from src.services.core_engines.xray_config_processor import XrayConfigProcessor
        from src.services.monitoring import ConnectionMonitoringService, MonitorSignal

        # Store MonitorSignal for use in signal handler
        self._MonitorSignal = MonitorSignal

        self._app_context = app_context
        self._xray_processor = XrayConfigProcessor(app_context)
        legacy_config_service = LegacyConfigService(self._xray_processor)

        xray_service = XrayService()
        singbox_service = SingboxService()

        # State
        self._current_connection = None
        self._reconnect_event_listener = None
        self._state_lock = threading.Lock()
        self._reconnect_lock = threading.Lock()
        self._session_id = 0  # Unique ID for each connection session
        self._pending_stop_engines: set = set()  # engines awaiting stop event (H2 gate)

        # Initialize ConnectionMonitoringService (creates its own monitors internally).
        self._monitoring = ConnectionMonitoringService(
            app_context=app_context,
            on_signal=self._handle_signal,
            on_reconnect=self._reconnect_internal,
            on_reconnect_event=self._emit_event,
        )

        # Create ConnectionOrchestrator with all dependencies. The TUN engine is
        # selected dynamically at connect time (Xray native TUN vs sing-box TUN).
        self._orchestrator = ConnectionOrchestrator(
            app_context=app_context,
            network_validator=self._monitoring.network_validator,
            xray_processor=self._xray_processor,
            xray_service=xray_service,
            legacy_config_service=legacy_config_service,
            singbox_service=singbox_service,
        )

        from src.services.monitoring.core_health_monitor import CoreHealthMonitor

        self._health_monitor = CoreHealthMonitor(
            xray_service=xray_service,
            singbox_service=singbox_service,
        )

        # React to unexpected core-process crashes (published by CoreHealthMonitor)
        # and to graceful core-process stop completions. Keeps the deterministic
        # ConnectionFSM / session state in sync even when the crash bypasses the
        # normal connect/disconnect flow.
        from src.core.event_bus import (
            EVENT_CORE_CRASHED,
            EVENT_CORE_PROCESS_STOPPED,
            EVENT_NETWORK_INTERFACE_CHANGED,
            event_bus,
        )

        self._core_crash_event = EVENT_CORE_CRASHED
        self._core_process_stopped_event = EVENT_CORE_PROCESS_STOPPED
        event_bus.subscribe(EVENT_CORE_CRASHED, self._handle_core_crash)
        event_bus.subscribe(EVENT_CORE_PROCESS_STOPPED, self._handle_core_process_stopped)
        event_bus.subscribe(EVENT_NETWORK_INTERFACE_CHANGED, self._handle_network_interface_changed)

        # Connection Adoption: Check if services are already running (CLI persistence)
        self._adopt_existing_connection()

    def _handle_signal(self, signal, payload: dict = None):
        """
        Handle monitor signals - SINGLE POINT OF SIGNAL->EVENT CONVERSION.

        This is the ONLY place where signals become user-visible events.
        All policy decisions (emit event? trigger reconnect?) happen here.

        Args:
            signal: MonitorSignal enum value
            payload: Optional fact container from the emitting monitor
                (e.g. ``{"source": "xray", "line": "..."}``).
        """
        # Get current connection state (thread-safe)
        with self._state_lock:
            current_conn = self._current_connection
            session_valid = self._session_id > 0

        # CRITICAL: Ignore all signals if no valid session
        # This prevents late signals after disconnect
        if not session_valid or not current_conn:
            logger.debug(f"[ConnectionManager] Signal {signal.name} ignored (no valid session)")
            return

        # SIGNAL -> EVENT MAPPING (single source of truth)
        if signal == self._MonitorSignal.PASSIVE_FAILURE:
            # Passive log detected failure (Xray-core or sing-box TUN) - trigger reconnect
            source = (payload or {}).get("source", "core")
            logger.warning(f"[ConnectionManager] Passive failure detected (source: {source})")
            self._monitoring.handle_failure(current_conn)

        elif signal == self._MonitorSignal.ACTIVE_LOST:
            # Active monitor detected connectivity loss
            logger.warning("[ConnectionManager] Active monitor: connectivity lost")
            self._emit_event("connectivity_lost")
            self._monitoring.handle_failure(current_conn)

        elif signal == self._MonitorSignal.ACTIVE_DEGRADED:
            # Active monitor detected degradation (soft warning - no reconnect)
            logger.info("[ConnectionManager] Active monitor: connectivity degraded")
            self._emit_event("connectivity_degraded")

        elif signal == self._MonitorSignal.ACTIVE_RESTORED:
            # Active monitor detected recovery
            logger.info("[ConnectionManager] Active monitor: connectivity restored")
            self._emit_event("connectivity_restored")

    def _handle_core_crash(self, payload=None) -> None:
        """Hard-reset the connection session when a core process crashes.

        Subscribed to ``EVENT_CORE_CRASHED`` (published by CoreHealthMonitor).
        Guarantees a deterministic teardown on crash:
        - Monitoring + auto-reconnect are cancelled (no zombie reconnect loop).
        - The current session is invalidated so late signals/events are ignored.
        - The FSM/UI is driven to DISCONNECTED via the normal ``disconnected`` event.
        - THEN, if auto-reconnect is enabled, a fresh reconnect of the crashed
          session is scheduled (the #1 use case for auto-reconnect).
        """
        with self._state_lock:
            if self._session_id <= 0 or not self._current_connection:
                logger.debug(f"[ConnectionManager] Core crash event ignored (no active session): {payload}")
                return
            logger.warning("[ConnectionManager] Core crash detected — hard reset of connection session")
            crashed_connection = dict(self._current_connection)
            self._current_connection = None
            self._session_id = 0

        # Stop monitoring + auto-reconnect and the health monitor loop itself.
        self._monitoring.stop()
        self._health_monitor.stop_monitoring()

        # Emit disconnected through the canonical path so the FSM transitions to
        # DISCONNECTED and the UI (DashboardPage, tray, etc.) resets reactively.
        self._emit_event("disconnected", {"reason": "core_crashed", "crash_payload": payload})

        # Schedule an automatic reconnect for the crashed session. This runs on
        # a daemon thread: the crash handler itself executes on the health
        # monitor's polling thread, and connect() blocks until the new session
        # is established.
        self._schedule_crash_reconnect(crashed_connection)

    def _schedule_crash_reconnect(self, crashed_connection: dict) -> None:
        """Auto-reconnect after a core crash (if the feature is enabled).

        A small initial delay lets the OS release the dead process's handles
        and gives transient crashes (OOM, port still bound) time to clear. The
        reconnect goes through ``_reconnect_internal`` → ``connect()`` which
        owns a brand-new session and emits ``connecting``/``connected`` so the
        full UI flow replays naturally.
        """
        import threading

        def _worker():
            try:
                # Let the crashed process fully die and ports/handles release.
                time.sleep(3.0)

                # Respect the user's battery-saver choice at reconnect time.
                if not self._app_context.settings.get_auto_reconnect_enabled():
                    logger.info("[ConnectionManager] Auto-reconnect disabled — not recovering from core crash")
                    return

                file_path = crashed_connection.get("file")
                mode = crashed_connection.get("mode")
                if not file_path or file_path == "Adopted Connection":
                    logger.warning(
                        "[ConnectionManager] Cannot auto-reconnect adopted/crashed session without a config file"
                    )
                    return

                logger.info(f"[ConnectionManager] Auto-reconnecting after core crash ({mode})...")
                success = self._reconnect_internal(file_path, mode, crashed_connection)
                if success:
                    logger.info("[ConnectionManager] Post-crash reconnect succeeded")
                else:
                    logger.error("[ConnectionManager] Post-crash reconnect failed")
                    self._emit_event("reconnect_failed", {"reason": "crash_reconnect_failed"})
            except Exception as e:
                logger.error(f"[ConnectionManager] Post-crash reconnect error: {e}")

        threading.Thread(target=_worker, daemon=True, name="CrashReconnect").start()

    def _handle_core_process_stopped(self, payload=None) -> None:
        """Transition FSM to DISCONNECTED once teardown has fully completed.

        Subscribed to ``EVENT_CORE_PROCESS_STOPPED`` (published by
        ``XrayService.stop`` / ``SingboxService.stop``). In dual-engine (TUN/VPN)
        mode two stop events are published; the FSM must NOT flip to DISCONNECTED
        on the first one while the remaining engine (and the red disconnecting
        animation) is still running.

        IMPORTANT (H2 fix): we no longer trust ``_engine_is_running`` as the gate,
        because each ``stop()`` zeroes its PID BEFORE publishing the event, so
        ``is_running`` reads False before teardown actually completes. Instead we
        count the stop events we have actually RECEIVED against the set of engines
        that were running, and only transition once every expected engine has
        reported stop — eliminating the premature DISCONNECTED flip.
        """
        try:
            from src.core.fsm.connection_fsm import ConnectionState, connection_fsm

            if connection_fsm.state != ConnectionState.STOPPING:
                return

            engine = (payload or {}).get("engine")
            orchestrator = getattr(self, "_orchestrator", None)
            if engine is None or orchestrator is None:
                # No engine info available — fall back to the general gate.
                if self._engines_stopped():
                    connection_fsm.transition_to(ConnectionState.DISCONNECTED, payload=payload or {})
                return

            running_engines = self._running_orchestrator_engines()
            # Snapshot once: only persist the expected set on the FIRST stop event
            # (so a later recompute of `is_running` — which both stop()s zero
            # before publishing — cannot re-inflate the expected set). The
            # discard must target the SAME set object stored on self, so we build
            # the expected set in place rather than via a fresh copy in
            # _set_expected_stopped (a copy would lose the discard).
            # init via getattr so __new__-only instances (tests) don't raise
            if not getattr(self, "_pending_stop_engines", None):
                self._pending_stop_engines = set(running_engines)
            self._pending_stop_engines.discard(engine)

            # Gate on the engines ACTUALLY no longer running (authoritative), not
            # merely "reported" — this is what fixes the premature transition in
            # dual-engine mode: while the sibling engine is still mid-teardown its
            # is_running() is still True, so the gate holds. Once both are fully
            # stopped (and we've confirmed the expected set drained OR the engine
            # that never ran was reported), we flip to DISCONNECTED.
            if self._engines_stopped() and (
                self._all_expected_engines_stopped() or engine not in self._running_orchestrator_engines()
            ):
                connection_fsm.transition_to(ConnectionState.DISCONNECTED, payload=payload or {})
        except Exception as e:
            logger.error(f"[ConnectionManager] Error syncing FSM on core process stop: {e}")

    def _handle_network_interface_changed(self, payload: dict = None):
        """React to network interface change event (link flap, Wi-Fi toggle, default gateway change)."""
        logger.info("[ConnectionManager] Physical network interface change detected")
        with self._state_lock:
            current_conn = self._current_connection
            session_valid = self._session_id > 0
            current_session = self._session_id

        if not session_valid or not current_conn:
            logger.debug("[ConnectionManager] Interface change ignored: no active session")
            return

        # Check FSM state: if already in STARTING, PREPARING, or STOPPING, a connect/reconnect is already in-flight!
        from src.core.fsm.connection_fsm import ConnectionState, connection_fsm

        fsm_state = connection_fsm.state
        if fsm_state in {ConnectionState.STARTING, ConnectionState.PREPARING, ConnectionState.STOPPING}:
            logger.info(
                f"[ConnectionManager] Connection or reconnection already in-flight (FSM: {fsm_state.value}). "
                "Skipping duplicate interface event."
            )
            return

        # Acquire non-blocking lock to avoid parallel reconnect workers
        if not self._reconnect_lock.acquire(blocking=False):
            logger.info(
                "[ConnectionManager] Reconnection worker already in-progress on another thread. "
                "Ignoring redundant interface event."
            )
            return

        def _reconnect_runner():
            try:
                # Reset backoff so reconnect can happen immediately on physical link change
                if hasattr(self._monitoring, "_auto_reconnect"):
                    self._monitoring._auto_reconnect.reset_backoff(reason="interface_change")
                logger.info(
                    f"[ConnectionManager] Triggering auto-reconnect on interface change (session {current_session})"
                )
                self._monitoring.handle_failure(current_conn)
            finally:
                self._reconnect_lock.release()

        threading.Thread(target=_reconnect_runner, daemon=True, name="InterfaceReconnectWorker").start()

    def _on_network_interface_changed(self):
        """Callback from WindowsInterfaceWatcher; emits to EventBus."""
        from src.core.event_bus import EVENT_NETWORK_INTERFACE_CHANGED, event_bus

        event_bus.publish(EVENT_NETWORK_INTERFACE_CHANGED, {})

    @staticmethod
    def _engine_is_running(service) -> bool:
        """Safely check whether a core engine service is still running.

        Handles ``is_running`` being a method, a property, or a plain bool, and
        tolerates missing services (None) or attributes.
        """
        if service is None:
            return False
        attr = getattr(service, "is_running", None)
        if attr is None:
            return False
        if callable(attr):
            try:
                return bool(attr())
            except Exception:
                return False
        return bool(attr)

    def _engines_stopped(self) -> bool:
        """Check whether BOTH Xray-core and Sing-box engines are fully stopped.

        When no orchestrator/services are bound (bare instances in tests), the
        engines are treated as stopped.
        """
        orchestrator = getattr(self, "_orchestrator", None)
        if orchestrator is None:
            return True
        xray = getattr(orchestrator, "_xray_service", None)
        singbox = getattr(orchestrator, "_singbox_service", None)
        return not self._engine_is_running(xray) and not self._engine_is_running(singbox)

    def _running_orchestrator_engines(self) -> set:
        """Compute the set of engine names currently running via the orchestrator.

        Returns a subset of {"xray", "singbox"}. When no orchestrator is bound
        (bare instance / tests) returns "xray" as the expected single engine so
        the stop-event gate can still proceed.
        """
        orchestrator = getattr(self, "_orchestrator", None)
        if orchestrator is None:
            return {"xray"}
        engines = set()
        xray = getattr(orchestrator, "_xray_service", None)
        singbox = getattr(orchestrator, "_singbox_service", None)
        if self._engine_is_running(xray):
            engines.add("xray")
        if self._engine_is_running(singbox):
            engines.add("singbox")
        return engines or {"xray"}  # fallback: at least Xray expected in proxy mode

    def _all_expected_engines_stopped(self) -> bool:
        """True once every engine we expect to stop has published its stop event."""
        return not getattr(self, "_pending_stop_engines", set())

    def _adopt_existing_connection(self):
        """Adopt an already running connection (from PID files)."""
        xray_pid = self._orchestrator._xray_service.pid
        singbox_pid = self._orchestrator._singbox_service.pid if self._orchestrator._singbox_service else None

        if xray_pid or singbox_pid:
            # Single-process (Xray) or dual-engine (Xray proxy + sing-box TUN)
            # architecture: determine mode from the saved config if available,
            # or default to proxy.
            mode = self._detect_mode_from_running_config()
            self._session_id += 1
            self._current_connection = {
                "mode": mode,
                "xray_pid": xray_pid,
                "singbox_pid": singbox_pid,
                "file": t("connection.adopted_connection", default="Adopted Connection"),
                "session_id": self._session_id,
            }
            logger.debug(f"[ConnectionManager] Adopted existing {mode} connection (session {self._session_id})")

            # Start monitoring via facade (single decision point)
            self._monitoring.start(self._session_id, mode=mode)

    def _detect_mode_from_running_config(self) -> str:
        """Detect connection mode from the running Xray config (tun inbound = vpn)."""
        try:
            import json

            with open(OUTPUT_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
            inbounds = config.get("inbounds", [])
            if any(ib.get("protocol") == PROTOCOL_TUN for ib in inbounds):
                return MODE_VPN
        except Exception:
            pass
        return MODE_PROXY

    def connect(self, file_path: str, mode: str, step_callback=None) -> bool:
        """
        Establish connection using specified configuration file.

        Args:
            file_path: Path to configuration file
            mode: Connection mode ("vpn" or "proxy")
            step_callback: Optional callback for connection steps

        Returns:
            True if connection successful, False otherwise
        """
        # Emit connecting state
        self._emit_event("connecting")

        with self._state_lock:
            if self._current_connection:
                logger.debug("Stopping existing connection before new connection")
                self._monitoring.stop()
                self._orchestrator.teardown_connection(self._current_connection)
                self._current_connection = None

            # Create new session
            self._session_id += 1
            current_session = self._session_id

        success, connection_info = self._orchestrator.establish_connection(file_path, mode, step_callback)

        with self._state_lock:
            # Verify we're still in the same session (not cancelled)
            if self._session_id != current_session:
                logger.warning("[ConnectionManager] Session changed during connect, aborting")
                return False

            if success:
                connection_info["session_id"] = current_session
                self._current_connection = connection_info
                logger.info(f"[ConnectionManager] Connection established in {mode} mode (session {current_session})")

                # Start monitoring via facade (single decision point)
                config, _ = self._app_context.load_config(file_path)
                transport_type = self._xray_processor.get_transport_type(config) if config else None
                self._monitoring.start(current_session, mode=mode, transport_type=transport_type)
                self._health_monitor.start_monitoring()

                # Start OS network interface watcher for link/gateway change detection
                try:
                    from src.platform.factory import get_network_adapter

                    get_network_adapter().start_interface_watcher(self._on_network_interface_changed)
                except Exception as e:
                    logger.debug(f"[ConnectionManager] Could not start interface watcher: {e}")

                # Emit connected state
                self._emit_event(
                    "connected",
                    {"connected_at": connection_info.get("connected_at") or time.time()},
                )
            else:
                self._emit_event("connect_failed")

        return success

    def _reconnect_internal(self, file_path: str, mode: str, connection_info: Optional[dict] = None) -> bool:
        """Internal reconnect method for AutoReconnectService (no step_callback).

        A reconnect is a FRESH connection attempt that owns its own session:
        - ``connect()`` bumps ``_session_id`` and teardowns the previous engine,
          so the OLD session is invalidated by design (no stale events).
        - The failure that triggered the reconnect belongs to the OLD session;
          the reconnect itself is a brand-new session that emits "connected"
          when it succeeds.
        """
        return self.connect(file_path, mode, step_callback=None)

    def disconnect(self) -> bool:
        """
        Disconnect current connection.

        This is a HARD OVERRIDE:
        - Immediately cancels all reconnect attempts
        - Stops all monitoring (active and passive)
        - Invalidates current session to prevent late signals/events
        - No automatic restart is possible after this
        """
        # Emit disconnecting state FIRST (user-visible)
        self._emit_event("disconnecting")

        # Stop monitoring via facade (handles all: cancel reconnect, stop monitors)
        # After this, no signals will be forwarded
        self._monitoring.stop()
        self._health_monitor.stop_monitoring()

        # Stop OS network interface watcher
        try:
            from src.platform.factory import get_network_adapter

            get_network_adapter().stop_interface_watcher()
        except Exception as e:
            logger.debug(f"[ConnectionManager] Could not stop interface watcher: {e}")

        with self._state_lock:
            if not self._current_connection:
                self._emit_event("disconnected")
                return True
            connection = self._current_connection
            self._current_connection = None
            # Invalidate session to prevent any late signals
            self._session_id = 0

        # Teardown connection
        self._orchestrator.teardown_connection(connection)
        logger.info("[ConnectionManager] Disconnected successfully (hard override)")

        # Emit final state
        self._emit_event("disconnected")
        return True

    def cleanup(self):
        """Cleanup connection resources on exit."""
        # Unsubscribe reactive handlers to avoid leaking bound-method references.
        try:
            from src.core.event_bus import event_bus

            event_bus.unsubscribe(self._core_crash_event, self._handle_core_crash)
            event_bus.unsubscribe(self._core_process_stopped_event, self._handle_core_process_stopped)
        except Exception:
            pass
        # disconnect() already calls teardown_connection() — do not call it again
        # (would double-stop services and log confusing duplicate 'Stopped' messages).
        self.disconnect()

    def set_reconnect_event_listener(self, callback):
        """
        Set a callback to be notified of connection state changes.

        Args:
            callback: Function that accepts (event_type: str, data: dict)

        Events:
            - connecting: Connection attempt starting
            - connected: Connection established
            - connect_failed: Connection failed
            - failure_detected: Connection lost (auto-reconnect starting)
            - reconnecting: Auto-reconnect in progress
            - reconnected: Auto-reconnect succeeded
            - reconnect_failed: Auto-reconnect failed
            - connectivity_lost: Active monitor detected stall
            - connectivity_degraded: Soft warning (connection issues)
            - connectivity_restored: Active monitor detected recovery
            - disconnecting: User initiated disconnect
            - disconnected: Disconnect complete
        """
        self._reconnect_event_listener = callback

    def _emit_event(self, event_type: str, data: dict = None):
        """
        Emit a user-visible event to the listener.

        This is the ONLY method that emits events to the UI.
        """
        logger.debug(f"[ConnectionManager] Event: {event_type}")
        if self._reconnect_event_listener:
            try:
                self._reconnect_event_listener(event_type, data or {})
            except Exception as e:
                logger.error(f"[ConnectionManager] Error in event listener: {e}")

        # Synchronize ConnectionFSM deterministic states.
        #
        # SINGLE-PUBLISHER CONTRACT: ConnectionManager is the ONLY component
        # that broadcasts connection state over the EventBus. The FSM is pure
        # (it validates transitions and returns; it never publishes). So every
        # _emit_event call publishes TOPIC_CONNECTION_STATE_CHANGED EXACTLY
        # ONCE — whether the event mapped to a successful FSM transition, was
        # blocked, or is a UI-only event with no FSM mapping (e.g.
        # "failure_detected", "reconnecting", "connectivity_*").
        fsm_transitioned = False
        try:
            from src.core.fsm.connection_fsm import ConnectionState, connection_fsm

            if event_type == "connecting":
                # "connecting" always leads to PREPARING, but the FSM only
                # accepts PREPARING from STARTING (or DISCONNECTED). From the
                # pre-connect states PINGING (user clicked Connect during the
                # latency check) and ERROR (user retries after a failure) the
                # strict chain is PINGING/ERROR -> STARTING -> PREPARING —
                # route through STARTING first instead of leaving the FSM
                # stuck in the current state.
                current_state = connection_fsm.state
                if current_state in {
                    ConnectionState.PINGING,
                    ConnectionState.ERROR,
                }:
                    connection_fsm.transition_to(ConnectionState.STARTING, payload=data)
                elif current_state == ConnectionState.CONNECTED:
                    # Hot reconnection: transition from CONNECTED -> STOPPING first, then PREPARING
                    connection_fsm.transition_to(ConnectionState.STOPPING, payload=data)
                fsm_transitioned = connection_fsm.transition_to(ConnectionState.PREPARING, payload=data)
            elif event_type in ("connected", "reconnected"):
                fsm_transitioned = connection_fsm.transition_to(ConnectionState.CONNECTED, payload=data)
            elif event_type == "disconnecting":
                # User-requested stop. From ERROR there is no teardown to run,
                # so treat the request as a defensive reset to DISCONNECTED
                # (the FSM's legal exit from ERROR) rather than blocking and
                # leaving the FSM stuck in ERROR.
                if connection_fsm.state == ConnectionState.ERROR:
                    fsm_transitioned = connection_fsm.transition_to(ConnectionState.DISCONNECTED, payload=data)
                else:
                    fsm_transitioned = connection_fsm.transition_to(ConnectionState.STOPPING, payload=data)
            elif event_type in ("disconnected",):
                fsm_transitioned = connection_fsm.transition_to(ConnectionState.DISCONNECTED, payload=data)
            elif event_type in ("connect_failed", "reconnect_failed"):
                fsm_transitioned = connection_fsm.transition_to(ConnectionState.ERROR, payload=data)
        except Exception as e:
            logger.error(f"[ConnectionManager] Error updating FSM state for '{event_type}': {e}")

        # Publish EXACTLY ONCE (single publisher — the FSM no longer publishes).
        try:
            from src.core.event_bus import TOPIC_CONNECTION_STATE_CHANGED, EngineEvent, event_bus

            state = connection_fsm.state.value
            event_bus.publish(
                TOPIC_CONNECTION_STATE_CHANGED,
                EngineEvent(
                    event_name=event_type,
                    source="connection_manager",
                    payload={
                        "event": event_type,
                        "data": data or {},
                        "state": state,
                        "old_state": state if fsm_transitioned else None,
                        "new_state": state if fsm_transitioned else None,
                    },
                ),
            )
        except Exception as e:
            logger.error(f"[ConnectionManager] Error publishing event '{event_type}': {e}")
