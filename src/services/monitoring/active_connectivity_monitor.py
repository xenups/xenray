"""
Active Connectivity Monitor - Real connectivity probing with smart escalation.

Detects actual connectivity loss by probing the live tunnel:
- LIGHT probe (default): a cheap ``socket.create_connection`` to the local
  SOCKS proxy port (proves the proxy engine is alive and listening).
- HEAVY probe (only after N suspicious samples): an HTTP ``generate_204``
  request THROUGH the SOCKS proxy (proves end-to-end tunnel routing).

Resource budget (important):
- In a healthy session the monitor only opens ONE cheap local socket every
  SAMPLE_INTERVAL (3s). No HTTP requests are made while connectivity looks
  fine.
- The HTTP probe only runs when the light probe fails repeatedly or the stall
  counter reaches WARNING_SAMPLES / MAX_STALL_SAMPLES — i.e. rarely.
- All probes run on the dedicated daemon monitor thread with short timeouts
  (<=5s); nothing ever touches the UI thread.
"""

import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from loguru import logger


class ActiveConnectivityMonitor:
    """
    Monitors connectivity using real probes (SOCKS socket + HTTP 204).

    Detection Logic:
    1. Light probe: can we connect to the local SOCKS proxy port?
       - Yes  -> connection is fine (reset stall counter, emit RESTORED if needed)
       - No   -> increment stall counter; escalate to the HTTP probe
    2. Heavy probe (HTTP generate_204 THROUGH the proxy): only after
       REQUIRED_SAMPLES consecutive light-probe failures, or at
       WARNING_SAMPLES / MAX_STALL_SAMPLES.
       - Yes  -> tunnel works (idle system) — reset
       - No   -> real connectivity loss — emit LOST (after confirmation)
    3. Warmup grace for slow-handshake transports (xhttp/splithttp).
    """

    SAMPLE_INTERVAL = 3.0  # seconds between samples
    REQUIRED_SAMPLES = 2  # consecutive failures for fast detection (~6s)
    WARNING_SAMPLES = 4  # show warning in UI after this many (~12s)
    MAX_STALL_SAMPLES = 8  # failsafe: trigger after this many (~24s)
    # FP guard: the heavy (HTTP) probe must fail on this many CONSECUTIVE
    # samples before LOST fires. A single curl hiccup (DNS blip, endpoint
    # rate-limit, momentary CPU spike) is then absorbed instead of tearing
    # down a healthy session. With SAMPLE_INTERVAL=3s this costs ~3s extra
    # detection latency in the true-outage case — an acceptable trade.
    REQUIRED_LOST_CONFIRMATIONS = 2

    # Timeouts (short — never block the monitor thread for long)
    SOCKET_TIMEOUT = 2.0  # light probe (local socket)
    HTTP_TIMEOUT = 5.0  # heavy probe (end-to-end)

    # Transports that need warmup grace period (slower initial handshake)
    SLOW_HANDSHAKE_TRANSPORTS = {"xhttp", "splithttp"}

    # Probe target rotation pool for secondary heavy probing
    PROBE_TARGETS = [
        "https://cp.cloudflare.com/generate_204",
        "https://www.gstatic.com/generate_204",
        "https://connectivitycheck.gstatic.com/generate_204",
        "http://www.gstatic.com/generate_204",
    ]

    def __init__(
        self,
        socks_port_getter: Optional[Callable[[], int]] = None,
        on_connectivity_lost: Optional[Callable[[], None]] = None,
        on_connectivity_restored: Optional[Callable[[], None]] = None,
        on_connectivity_degraded: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize the monitor.

        Args:
            socks_port_getter: Callable returning the current SOCKS proxy port.
            on_connectivity_lost: Callback when connectivity is lost.
            on_connectivity_restored: Callback when connectivity is restored.
            on_connectivity_degraded: Callback when connection shows issues (soft warning).
        """
        self._socks_port_getter = socks_port_getter
        self._on_lost = on_connectivity_lost
        self._on_restored = on_connectivity_restored
        self._on_degraded = on_connectivity_degraded

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # State
        self._stall_samples = 0
        self._is_connected = True
        self._warning_emitted = False  # Track if warning already shown
        self._lost_confirmations = 0  # consecutive heavy-probe failures toward LOST
        self._needs_warmup = False  # True for transports with slow handshake (xhttp)
        self._handshake_complete = True  # Set to False during warmup phase
        self._session_id = 0  # Current session for event validation
        self._last_total_bytes = 0  # For backward-compatibility
        self._last_rx_bytes = 0  # For TUN-scoped RX throughput-gated lazy probing

        # Single bounded executor for event callbacks (max 1 worker — no
        # unbounded daemon thread spawning per emitted event).
        self._callback_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ActiveConnectivityMonitor-Callback"
        )

    def start(self, transport_type: str = None, session_id: int = 0):
        """
        Start the monitoring thread.

        Args:
            transport_type: Optional transport type (e.g., 'xhttp', 'ws').
                           Used to apply warmup grace for slow-handshake transports.
            session_id: Connection session ID for event validation.
        """
        with self._lock:
            if self._running:
                return

            self._running = True
            self._session_id = session_id
            self._stall_samples = 0
            self._is_connected = True
            self._warning_emitted = False
            self._lost_confirmations = 0
            self._last_total_bytes = 0
            self._last_rx_bytes = 0
            self._stop_event.clear()
            # Recreate the callback executor if a previous stop() shut it down
            # (supports start → stop → start on the same instance).
            if self._callback_executor._shutdown:
                self._callback_executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="ActiveConnectivityMonitor-Callback"
                )

            # Apply warmup grace for slow-handshake transports (xhttp)
            self._needs_warmup = transport_type in self.SLOW_HANDSHAKE_TRANSPORTS if transport_type else False
            self._handshake_complete = not self._needs_warmup

            self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="ActiveConnectivityMonitor")
            self._thread.start()

            warmup_info = f", warmup={transport_type}" if self._needs_warmup else ""
            logger.info(
                f"[ActiveConnectivityMonitor] Started session {session_id} "
                f"(fast={self.REQUIRED_SAMPLES}, failsafe={self.MAX_STALL_SAMPLES}{warmup_info})"
            )

    def stop(self):
        """Stop the monitoring thread immediately. Prevents any further event emissions."""
        with self._lock:
            if not self._running:
                return

            self._running = False
            self._session_id = 0  # Invalidate session to prevent late events
            self._stop_event.set()

            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)

            self._thread = None
            self._callback_executor.shutdown(wait=False)
            logger.info("[ActiveConnectivityMonitor] Stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _monitor_loop(self):
        """Main monitoring loop."""
        try:
            while not self._stop_event.is_set():
                self._check_connectivity()
                self._stop_event.wait(self.SAMPLE_INTERVAL)
        except Exception as e:
            logger.error(f"[ActiveConnectivityMonitor] Error in monitor loop: {e}")

    def _check_connectivity(self):
        """Check connectivity using lazy throughput gating and SOCKS5 tunnel escalation."""
        port = self._socks_port_getter() if self._socks_port_getter else 10805

        # 1. PRIMARY: Lazy throughput gating
        # If live traffic is actively flowing, connection is demonstrably alive.
        # Suppress active probes to prevent unnecessary DPI exposure.
        if self._check_traffic_flow():
            self._on_healthy()
            return

        # 2. SECONDARY: When idle or low throughput, probe SOCKS5 tunnel
        if self._probe_socks_socket(port):
            self._on_healthy()
            return

        # 3. Tunnel probe failed -> suspicious / stalled
        self._stall_samples += 1
        logger.debug(f"[ActiveConnectivityMonitor] Tunnel probe failed ({self._stall_samples}/{self.REQUIRED_SAMPLES})")

        # Soft warning: show UI feedback after WARNING_SAMPLES
        if self._stall_samples == self.WARNING_SAMPLES and not self._warning_emitted:
            if self._verify_connectivity(port):
                # Heavy probe succeeded - system is just idle, not offline
                logger.debug("[ActiveConnectivityMonitor] Stall but HTTP probe OK - system is idle")
                self._stall_samples = 0
            else:
                # Heavy probe failed - connection is degraded
                self._warning_emitted = True
                logger.info("[ActiveConnectivityMonitor] Connection degraded - probe failed")
                self._emit_degraded()

        # HYBRID ESCALATION with FP confirmation guard:
        if self._stall_samples >= self.REQUIRED_SAMPLES:
            if not self._verify_connectivity(port):
                self._lost_confirmations += 1
                logger.debug(
                    f"[ActiveConnectivityMonitor] Heavy probe failed "
                    f"({self._lost_confirmations}/{self.REQUIRED_LOST_CONFIRMATIONS})"
                )
            else:
                # Heavy probe OK - connection is fine (idle), reset everything
                logger.info("[ActiveConnectivityMonitor] HTTP probe OK - connection is fine, resetting")
                self._stall_samples = 0
                self._warning_emitted = False
                self._lost_confirmations = 0

        confirmed = self._lost_confirmations >= self.REQUIRED_LOST_CONFIRMATIONS or (
            self._stall_samples >= self.MAX_STALL_SAMPLES
            and not self._verify_connectivity(port)
        )

        if confirmed and self._is_connected:
            self._is_connected = False
            self._lost_confirmations = 0
            reason = (
                f"confirmed by {self.REQUIRED_LOST_CONFIRMATIONS} consecutive HTTP probe failures "
                f"(after {self._stall_samples} stalled samples)"
            )
            logger.warning(f"[ActiveConnectivityMonitor] Connectivity LOST ({reason})")
            self._emit_lost()

    def _get_tun_io_counters(self):
        """Extract I/O counters strictly for the active TUN interface.

        Resolves against PlatformUtils.get_tun_interface_name() ('SINGTUN' on Windows),
        with case-insensitive matching and specific XenRay aliases ('xenray-tun', 'singtun').
        Generic driver names like 'wintun' are explicitly excluded to prevent false-binding
        to third-party VPN adapters.
        """
        try:
            import psutil
            per_nic = psutil.net_io_counters(pernic=True)
            if not per_nic:
                return None

            from src.utils.platform_utils import PlatformUtils
            target_name = PlatformUtils.get_tun_interface_name()

            # 1. Exact match (primary)
            if target_name in per_nic:
                return per_nic[target_name]

            # 2. Case-insensitive exact match or XenRay-specific TUN alias
            target_lower = target_name.lower()
            for name, stats in per_nic.items():
                name_lower = name.lower()
                if name_lower == target_lower or name_lower in ("singtun", "xenray-tun"):
                    return stats
        except Exception as e:
            logger.debug(f"[ActiveConnectivityMonitor] Error querying TUN counters: {e}")
        return None

    def _check_traffic_flow(self) -> bool:
        """PRIMARY: Lazy throughput gate strictly on the TUN interface and RX payload.

        In TUN/VPN mode:
        Only incoming payload (bytes_recv) confirms that the remote proxy server is
        actively delivering response data. Outgoing traffic (bytes_sent) during WAN
        outages consists of unacknowledged TCP SYN retries and must never be treated
        as evidence of a live connection.

        In Proxy mode (system proxy):
        No TUN adapter is instantiated. _get_tun_io_counters returns None, safely
        bypassing the throughput gate and allowing the lightweight SOCKS5 active
        heartbeat to run every 3s to guarantee immediate failure detection without TUN metrics.
        """
        stats = self._get_tun_io_counters()
        if not stats:
            return False

        now_rx = stats.bytes_recv

        # Adapter rebuild / counter reset / wrap-around guard:
        # If the TUN adapter was recreated during reconnect, or if the OS network
        # byte counter rolled over (uint32/uint64 wrap-around on long-running sessions),
        # now_rx will drop below _last_rx_bytes. Re-calibrate the baseline cleanly to now_rx
        # and do not gate on this tick (benign 1-tick fallthrough to SOCKS5 probe).
        if self._last_rx_bytes == 0 or now_rx < self._last_rx_bytes:
            self._last_rx_bytes = now_rx
            self._last_total_bytes = now_rx
            return False

        delta_rx = max(0, now_rx - self._last_rx_bytes)
        self._last_rx_bytes = now_rx
        self._last_total_bytes = now_rx

        return delta_rx >= 1024

    def _on_healthy(self):
        """Reset stall state and emit RESTORED if we were in LOST/degraded."""
        was_warning_shown = self._warning_emitted
        was_lost = not self._is_connected

        if self._stall_samples > 0:
            logger.debug("[ActiveConnectivityMonitor] Tunnel probe OK, resetting stall counter")

        self._stall_samples = 0
        self._warning_emitted = False
        self._lost_confirmations = 0

        if was_lost:
            self._is_connected = True
            logger.info("[ActiveConnectivityMonitor] Connectivity RESTORED (was lost)")
            self._emit_restored()
        elif was_warning_shown:
            # Traffic resumed after degraded warning - clear the warning
            logger.info("[ActiveConnectivityMonitor] Connectivity RESTORED (clearing warning)")
            self._emit_restored()

    # ------------------------------------------------------------------
    # Probes
    # ------------------------------------------------------------------

    def _probe_socks_socket(self, port: int) -> bool:
        """Backward-compatibility alias for tests and callers."""
        return self._probe_socks_tunnel(port)

    def _probe_socks_tunnel(self, port: int) -> bool:
        """Send SOCKS5 handshake & connect command to verify real remote tunnel reachability.

        Uses SOCKS5 ATYP=0x03 (Domain Name) to delegate DNS resolution strictly to the remote
        proxy core, guaranteeing zero client-side DNS leaks on the physical NIC.
        """
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=self.SOCKET_TIMEOUT) as s:
                # 1. SOCKS5 greeting: NO_AUTH (0x00)
                s.sendall(b"\x05\x01\x00")
                resp = s.recv(2)
                if len(resp) < 2 or resp[0] != 0x05 or resp[1] != 0x00:
                    return False

                # 2. SOCKS5 CONNECT to cp.cloudflare.com:80 via ATYP=0x03 (Domain Name)
                domain = b"cp.cloudflare.com"
                connect_cmd = b"\x05\x01\x00\x03" + bytes([len(domain)]) + domain + b"\x00\x50"
                s.sendall(connect_cmd)
                resp = s.recv(10)
                # SOCKS5 reply: resp[1] == 0x00 indicates success
                return len(resp) >= 2 and resp[1] == 0x00
        except OSError:
            return False

    def _probe_socks_socket(self, port: int) -> bool:
        """Backward-compatible delegate."""
        return self._probe_socks_tunnel(port)

    def _verify_connectivity(self, port: int) -> bool:
        """
        Heavy probe: HTTP generate_204 THROUGH SOCKS proxy with target rotation & jitter.

        Proves end-to-end routing (the tunnel actually forwards traffic).
        """
        try:
            import random
            from src.utils.network_utils import NetworkUtils

            target_url = random.choice(self.PROBE_TARGETS)
            jitter_timeout = self.HTTP_TIMEOUT * random.uniform(0.8, 1.2)

            result = NetworkUtils.check_proxy_connectivity(
                port=port,
                target_url=target_url,
                timeout=max(jitter_timeout, 2.0),
                retries=1,
            )

            if result:
                logger.debug(f"[ActiveConnectivityMonitor] HTTP probe OK via {target_url}")
            else:
                logger.debug(f"[ActiveConnectivityMonitor] HTTP probe failed via {target_url}")

            return result

        except Exception as e:
            logger.debug(f"[ActiveConnectivityMonitor] Probe error: {e}")

        return False

    # ------------------------------------------------------------------
    # Emitters (thread-safe, session-guarded)
    # ------------------------------------------------------------------

    def _emit_lost(self):
        """Emit connectivity lost event (only if still running)."""
        with self._lock:
            if not self._running:
                logger.debug("[ActiveConnectivityMonitor] Suppressed lost event (stopped)")
                return
        if self._on_lost:
            try:
                self._callback_executor.submit(self._on_lost)
            except RuntimeError:
                logger.debug("[ActiveConnectivityMonitor] Dropped lost event (callback executor shut down)")

    def _emit_restored(self):
        """Emit connectivity restored event (only if still running)."""
        with self._lock:
            if not self._running:
                logger.debug("[ActiveConnectivityMonitor] Suppressed restored event (stopped)")
                return
        if self._on_restored:
            try:
                self._callback_executor.submit(self._on_restored)
            except RuntimeError:
                logger.debug("[ActiveConnectivityMonitor] Dropped restored event (callback executor shut down)")

    def _emit_degraded(self):
        """Emit connectivity degraded (soft warning) event (only if still running)."""
        with self._lock:
            if not self._running:
                logger.debug("[ActiveConnectivityMonitor] Suppressed degraded event (stopped)")
                return
        if self._on_degraded:
            try:
                self._callback_executor.submit(self._on_degraded)
            except RuntimeError:
                logger.debug("[ActiveConnectivityMonitor] Dropped degraded event (callback executor shut down)")
