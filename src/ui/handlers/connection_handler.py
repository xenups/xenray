"""Connection Handler - Manages user-initiated connection lifecycle."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable, Optional

from src.core.app_context import AppContext
from src.core.connection_manager import ConnectionManager
from src.core.constants import TMPDIR, XRAY_LOG_FILE
from src.core.i18n import t
from src.core.logger import logger
from src.core.types import ConnectionMode
from src.services.monitoring.network_stats import NetworkStatsService


class ConnectionHandler:
    """
    Handles user-initiated connection lifecycle (connect, disconnect, reconnect).

    Responsibilities:
    - Coordinate connection/disconnection flows
    - Delegate to ConnectionManager for core logic
    - Update UI state through callbacks
    """

    def __init__(
        self,
        connection_manager: ConnectionManager,
        app_context: AppContext,
        network_stats: NetworkStatsService,
    ):
        self._connection_manager = connection_manager
        self._app_context = app_context
        self._network_stats = network_stats
        self._state_lock = threading.Lock()  # Thread safety for shared state

        # Operation generation token: bumped on every connect/disconnect/reconnect
        # initiation so stale background workers (e.g. a disconnect task that is
        # sleeping to let the disconnecting animation render) can detect they were
        # superseded by a newer user action and skip their trailing UI reset.
        self._generation = 0

        # UI components (set via setup)
        self._ui_helper = None
        self._connection_button = None
        self._status_display = None
        self._log_viewer = None
        self._toast = None
        self._systray = None
        self._logs_drawer_component = None
        self._latency_monitor_handler = None

        # State callbacks
        self._is_running_getter: Optional[Callable[[], bool]] = None
        self._is_running_setter: Optional[Callable[[bool], None]] = None
        self._connecting_getter: Optional[Callable[[], bool]] = None
        self._connecting_setter: Optional[Callable[[bool], None]] = None
        self._selected_profile_getter: Optional[Callable[[], Optional[dict]]] = None
        self._current_mode_getter: Optional[Callable[[], ConnectionMode]] = None
        self._update_horizon_glow_callback: Optional[Callable[[str], None]] = None
        self._profile_manager_is_running_setter: Optional[Callable[[bool], None]] = None
        self._monitoring_service_is_running_setter: Optional[Callable[[bool], None]] = None
        self._lan_card_callback: Optional[Callable[[bool], None]] = None

    def setup(
        self,
        ui_helper,
        connection_button,
        status_display,
        log_viewer,
        toast,
        systray,
        logs_drawer_component,
        latency_monitor_handler,
        is_running_getter,
        is_running_setter,
        connecting_getter,
        connecting_setter,
        selected_profile_getter,
        current_mode_getter,
        update_horizon_glow_callback,
        profile_manager_is_running_setter,
        monitoring_service_is_running_setter,
    ):
        """Bind UI components and state callbacks."""
        self._ui_helper = ui_helper
        self._connection_button = connection_button
        self._status_display = status_display
        self._log_viewer = log_viewer
        self._toast = toast
        self._systray = systray
        self._logs_drawer_component = logs_drawer_component
        self._latency_monitor_handler = latency_monitor_handler
        self._is_running_getter = is_running_getter
        self._is_running_setter = is_running_setter
        self._connecting_getter = connecting_getter
        self._connecting_setter = connecting_setter
        self._selected_profile_getter = selected_profile_getter
        self._current_mode_getter = current_mode_getter
        self._update_horizon_glow_callback = update_horizon_glow_callback
        self._profile_manager_is_running_setter = profile_manager_is_running_setter
        self._monitoring_service_is_running_setter = monitoring_service_is_running_setter

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def connect_async(self):
        """Start connection in background thread."""
        if self._is_connecting():
            return

        with self._state_lock:
            self._generation += 1
            current_gen = self._generation

        self._set_connecting(True)
        self._show_connecting_ui()
        threading.Thread(target=lambda: self._perform_connect_task(current_gen), daemon=True).start()

    def reconnect(self):
        """Fast reconnect for server switching while already connected."""
        if self._is_connecting():
            return

        with self._state_lock:
            self._generation += 1
            current_gen = self._generation

        self._set_connecting(True)
        self._show_connecting_ui()
        threading.Thread(target=lambda: self._fast_reconnect_task(current_gen), daemon=True).start()

    def disconnect(self):
        """Disconnect from VPN/Proxy.

        Clicking disconnect MUST immediately invalidate any in-flight connect
        worker and issue the process stop — it never waits for UI text-cycling
        animation timers.
        """
        is_running = self._is_running_getter() if self._is_running_getter else False
        if not is_running:
            return

        # Invalidate any pending connect/reconnect worker and any stale
        # disconnect task's trailing UI reset.
        with self._state_lock:
            self._generation += 1

        self._show_disconnecting_ui()
        threading.Thread(target=self._disconnect_task, daemon=True).start()

    # -------------------------------------------------------------------------
    # Thread-safe State Management
    # -------------------------------------------------------------------------

    def _is_connecting(self) -> bool:
        """Check if currently connecting (thread-safe)."""
        with self._state_lock:
            return self._connecting_getter() if self._connecting_getter else False

    def _set_connecting(self, value: bool):
        """Set connecting state (thread-safe)."""
        with self._state_lock:
            if self._connecting_setter:
                self._connecting_setter(value)

    def _set_running_state(self, running: bool):
        """Update all running state flags (thread-safe)."""
        with self._state_lock:
            if self._is_running_setter:
                self._is_running_setter(running)
            if self._profile_manager_is_running_setter:
                self._profile_manager_is_running_setter(running)
            if self._monitoring_service_is_running_setter:
                self._monitoring_service_is_running_setter(running)

    # -------------------------------------------------------------------------
    # UI Helpers (reduce duplication)
    # -------------------------------------------------------------------------

    def _ui_call(self, callback):
        """Safely execute UI callback on main thread."""
        if self._ui_helper and callback:
            self._ui_helper.call(callback)

    def _show_connecting_ui(self):
        """Show connecting state on button, status display, and horizon glow."""
        if self._connection_button:
            self._ui_call(self._connection_button.set_connecting)
        if self._status_display:
            self._ui_call(self._status_display.set_connecting)
        if self._update_horizon_glow_callback:
            self._ui_call(lambda: self._update_horizon_glow_callback("connecting"))

    def _show_disconnecting_ui(self):
        """Show the disconnecting red animation on the button + status + glow.

        The button's existing red pulse/glow animation is invoked here so it
        starts the instant the user requests a disconnect and persists while
        process teardown (``SingboxService.stop`` / ``XrayService.stop``) runs in
        the background. ``ConnectionButton.set_disconnecting`` drives the pulse;
        it is later stopped by ``set_disconnected`` when teardown completes.
        ``_ui_call`` is safe from the Flet loop thread (executes inline) and from
        background threads (systray) alike.
        """
        if self._connection_button:
            self._ui_call(self._connection_button.set_disconnecting)
        if self._status_display:
            self._ui_call(self._status_display.set_disconnecting)
        if self._update_horizon_glow_callback:
            self._ui_call(lambda: self._update_horizon_glow_callback("disconnecting"))

    def _show_connected_ui(self, profile_data: dict = None):
        """Show connected state in UI."""
        if self._status_display:
            self._ui_call(lambda: self._status_display.set_connected(country_data=profile_data))
        if self._connection_button:
            self._ui_call(self._connection_button.set_connected)
        if self._update_horizon_glow_callback:
            self._ui_call(lambda: self._update_horizon_glow_callback("connected"))
        if self._systray:
            self._systray.update_state()
        self._update_lan_card()

    def _update_lan_card(self, show: bool = True):
        """Show/hide the LAN sharing card based on connection + allow_lan state."""
        if not self._lan_card_callback:
            return
        if show and self._app_context:
            show = bool(self._app_context.settings.get_allow_lan())
        self._ui_call(lambda: self._lan_card_callback(show))

    def _show_toast(self, msg_key: str, toast_type: str = "error", duration: int = 3000):
        """Show toast notification."""
        if self._toast:
            method = getattr(self._toast, toast_type, self._toast.error)
            self._ui_call(lambda: method(t(msg_key), duration))

    def reset_ui_disconnected(self):
        """Reset UI to disconnected state."""
        self._set_running_state(False)
        self._set_connecting(False)

        try:
            if self._connection_button:
                self._connection_button.set_disconnected()
            if self._status_display:
                self._status_display.set_disconnected()
            if self._update_horizon_glow_callback:
                self._update_horizon_glow_callback("disconnected")
            if self._latency_monitor_handler:
                self._latency_monitor_handler.trigger_single_check()
        except Exception as e:
            logger.warning(f"[ConnectionHandler] Error resetting UI: {e}")
        self._update_lan_card(show=False)

    # -------------------------------------------------------------------------
    # Connection Task (broken into smaller methods)
    # -------------------------------------------------------------------------

    def _perform_connect_task(self, gen=None):
        """Core connection logic - runs in background thread.

        Args:
            gen: Operation generation captured at connect time. When a newer
                disconnect/reconnect superseded this worker, the UI-reset paths
                are skipped so stale frames never clobber the newer action.
        """
        if gen is not None and gen != self._generation:
            logger.debug("[ConnectionHandler] Connect task superseded, aborting")
            return
        try:
            if not self._check_internet(gen):
                return

            profile, mode_str = self._prepare_connection()
            if profile is None:
                return

            self._start_log_tailing(mode_str)
            config_path = self._write_temp_config(profile)

            if not self._establish_connection(config_path, mode_str, gen):
                return

            self._set_running_state(True)

            if not self._verify_post_connection():
                return

            self._finalize_connection(profile)

        except Exception as e:
            logger.error(f"[ConnectionHandler] Connection error: {e}")
            self._handle_connection_failure(gen)

    def _check_internet(self, gen=None) -> bool:
        """Check internet connectivity before connecting."""
        from src.utils.network_utils import NetworkUtils

        if not NetworkUtils.check_internet_connection():
            self._set_connecting(False)
            if gen is None or gen == self._generation:
                self._ui_call(self.reset_ui_disconnected)
            self._show_toast("connection.no_internet")
            return False
        return True

    def _prepare_connection(self) -> tuple:
        """Prepare connection parameters."""
        profile = self._selected_profile_getter() if self._selected_profile_getter else None
        mode = self._current_mode_getter() if self._current_mode_getter else ConnectionMode.PROXY
        mode_str = "vpn" if mode == ConnectionMode.VPN else "proxy"

        os.makedirs(TMPDIR, exist_ok=True)
        return profile, mode_str

    def _start_log_tailing(self, mode_str: str):
        """Start log viewer tailing — ONLY if the user explicitly enabled it.

        The logs panel starts OFF (zero CPU until the user hits Enable in the
        logs drawer). Connection events must not silently turn tailing on;
        they only refresh the tailer when the user already opted in.
        """
        if not self._log_viewer:
            return
        if not getattr(self._log_viewer, "user_enabled", False):
            logger.debug("[ConnectionHandler] Log tailing disabled by user — skipping auto-start")
            return

        try:
            app_log = os.path.join(TMPDIR, "xenray.log")
            self._log_viewer.start_tailing(app_log, XRAY_LOG_FILE)
        except Exception as e:
            logger.warning(f"[ConnectionHandler] Failed to start log tailing: {e}")

    def _write_temp_config(self, profile: dict) -> str:
        """Write temporary config file."""
        config_path = os.path.join(TMPDIR, "current_config.json")

        # Check if this is a chain
        is_chain = profile.get("_is_chain") or profile.get("items") is not None

        if is_chain:
            # Generate chain config using XrayConfigProcessor
            from src.services.core_engines.xray_config_processor import XrayConfigProcessor

            processor = XrayConfigProcessor(self._app_context)
            success, chain_config, error_or_tag = processor.build_chain_config(profile)
            if not success:
                logger.error(f"[ConnectionHandler] Failed to build chain config: {error_or_tag}")
                profile_config = {}
            else:
                profile_config = chain_config
                logger.info(f"[ConnectionHandler] Generated chain config with {len(profile.get('items', []))} items")
        else:
            profile_config = profile.get("config") if profile else {}

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(profile_config, f)

        return config_path

    def _establish_connection(self, config_path: str, mode_str: str, gen=None) -> bool:
        """Establish connection via ConnectionManager."""

        def on_step(msg: str):
            if self._status_display:
                self._ui_call(lambda: self._status_display.set_step(msg))
            if self._connection_button:
                self._ui_call(lambda: self._connection_button.set_step(msg))

        success = self._connection_manager.connect(config_path, mode_str, step_callback=on_step)

        if not success:
            self._set_connecting(False)
            if gen is None or gen == self._generation:
                self._ui_call(self.reset_ui_disconnected)
            self._show_toast("status.connection_failed")

        return success

    def _verify_post_connection(self) -> bool:
        """Lightweight post-connection sanity check after fragment warmup (soft).

        The connection was already verified by the orchestrator's health check
        before ``establish_connection`` returned. This re-check is advisory only:
        curl probes through the tunnel (especially sing-box ``strict_route`` WFP
        mode) can return false negatives once the TUN filters fully engage, so a
        failure here is logged but never tears down a healthy connection.
        """
        from src.utils.network_utils import NetworkUtils

        time.sleep(2.0)  # Allow the tunnel + fragmented/finalmask streams to stabilize

        mode = self._current_mode_getter() if self._current_mode_getter else ConnectionMode.PROXY
        proxy_port = self._app_context.settings.get_proxy_port() if self._app_context else 0

        # Quick re-check with one retry to ride out a transient stall. The outcome
        # is advisory — the connection stays connected regardless.
        for attempt in range(2):
            if self._post_connection_check(NetworkUtils, mode, proxy_port):
                return True
            if attempt < 1:
                logger.debug("[ConnectionHandler] Post-connection check transient failure, retrying...")
                time.sleep(1.0)

        # Soft failure: keep the connection. The orchestrator's health check
        # already verified it moments ago, so a flaky probe must not tear it down.
        logger.warning(
            "[ConnectionHandler] Post-connection re-check failed but connection kept "
            "(already verified by health check)"
        )
        return True

    @staticmethod
    def _post_connection_check(network_utils, mode, proxy_port: int) -> bool:
        """Verify the connection through the correct path for the active mode.

        In VPN/TUN mode all traffic is captured by the tunnel, so a raw direct
        socket check (e.g. to 8.8.8.8:53) is blocked by the TUN engine — the
        sing-box ``strict_route`` WFP filter rejects it with WinError 10013
        (WSAEACCES). Verify through the SOCKS proxy (the tunnel's egress path)
        instead, which works for both the Xray and sing-box TUN engines.
        """
        if mode == ConnectionMode.VPN:
            if not proxy_port:
                return False
            return network_utils.check_proxy_connectivity(proxy_port, timeout=3.0, retries=2)
        return network_utils.check_internet_connection()

    def _finalize_connection(self, profile: dict):
        """Finalize successful connection."""
        self._set_connecting(False)
        self._show_connected_ui(profile)
        self._start_network_stats()
        # If this server was never inspected (no cached location/latency), kick
        # off a one-off inspection now that we're connected so its country and
        # name propagate to the server list and dashboard via the event bus.
        self._inspect_unresolved_profile(profile)

    def _inspect_unresolved_profile(self, profile: dict) -> None:
        """Trigger a single inspection for a connected server that has no
        resolved location yet, then publish the result through the event bus.

        ``server_inspector.inspect`` submits a ping through the global queue and
        publishes ``TOPIC_SERVER_INSPECTED`` on completion — the same event the
        server list already uses to update a card live, and which the dashboard
        subscribes to so the country/name refresh immediately.
        """
        try:
            if not profile or not profile.get("config"):
                return
            # Already resolved (has a country or a measured latency) → skip.
            if profile.get("country_code") or profile.get("last_latency_val") is not None:
                return
            from src.services.connection.server_inspector import server_inspector

            server_inspector.inspect(profile)
        except Exception as e:
            logger.warning(f"[ConnectionHandler] Failed to schedule post-connect inspection: {e}")

    def _start_network_stats(self):
        """Start network stats monitoring."""
        if not self._network_stats:
            return

        try:
            self._network_stats.start()
            if self._logs_drawer_component:
                self._ui_call(lambda: self._logs_drawer_component.show_stats(True))
        except Exception as e:
            logger.warning(f"[ConnectionHandler] Failed to start network stats: {e}")

    def _handle_connection_failure(self, gen=None):
        """Handle connection failure cleanup."""
        self._set_connecting(False)
        if gen is None or gen == self._generation:
            self._ui_call(self.reset_ui_disconnected)

    # -------------------------------------------------------------------------
    # Reconnect Task
    # -------------------------------------------------------------------------

    def _fast_reconnect_task(self, gen=None):
        """Fast reconnect task - disconnect and reconnect immediately."""
        try:
            with self._state_lock:
                if gen is not None and gen != self._generation:
                    logger.debug("[ConnectionHandler] Reconnect superseded, aborting")
                    return

            self._set_running_state(False)

            try:
                self._connection_manager.disconnect()
            except Exception as e:
                logger.warning(f"[ConnectionHandler] Disconnect during reconnect: {e}")

            # If the user issued a disconnect while the fast-reconnect was
            # running, abort before starting a fresh connection.
            with self._state_lock:
                if gen is not None and gen != self._generation:
                    logger.debug("[ConnectionHandler] Reconnect cancelled after disconnect, aborting")
                    return

            self._perform_connect_task(gen)

        except Exception as e:
            logger.error(f"[ConnectionHandler] Reconnect error: {e}")
            self._handle_connection_failure(gen)

    # -------------------------------------------------------------------------
    # Disconnect Task
    # -------------------------------------------------------------------------

    def _disconnect_task(self):
        """Disconnect task - runs in background thread.

        Order matters: ``ConnectionManager.disconnect`` is invoked FIRST so the
        FSM transitions to STOPPING and the existing red disconnecting animation
        renders (and stays rendered) while process teardown runs. Only after the
        teardown completes (FSM -> DISCONNECTED) do we flip the running flags.

        The trailing ``reset_ui_disconnected`` is guarded by the generation token:
        if the user already started a new connection while this task was sleeping
        (to let the disconnecting animation render), the stale reset is skipped so
        it can never clobber the new CONNECTING state or skip initial connect steps.
        """
        with self._state_lock:
            gen = self._generation

        self._stop_network_stats()

        try:
            self._connection_manager.disconnect()
        except Exception as e:
            logger.warning(f"[ConnectionHandler] Disconnect error: {e}")

        self._set_running_state(False)
        self._stop_log_tailing()

        time.sleep(1.0)  # Allow UI to show disconnecting state

        with self._state_lock:
            if gen != self._generation:
                logger.debug("[ConnectionHandler] Disconnect superseded — skipping stale UI reset")
                return

        self._ui_call(self.reset_ui_disconnected)

        if self._systray:
            self._systray.update_state()

    def _stop_network_stats(self):
        """Stop network stats monitoring."""
        if not self._network_stats:
            return

        try:
            self._network_stats.stop()
            if self._logs_drawer_component:
                self._ui_call(lambda: self._logs_drawer_component.show_stats(False))
        except Exception as e:
            logger.warning(f"[ConnectionHandler] Failed to stop network stats: {e}")

    def _stop_log_tailing(self):
        """Stop log viewer tailing."""
        if not self._log_viewer:
            return

        try:
            self._log_viewer.stop_tailing()
        except Exception as e:
            logger.warning(f"[ConnectionHandler] Failed to stop log tailing: {e}")
