"""
Passive Log Monitor Service.

Monitors the core engine logs (Xray-core AND sing-box TUN engine) for
connection failures and triggers callbacks.

Key design points:
- ONE tailer thread for ALL log files (no per-file threads) — each tick only
  stats the files and reads NEW bytes from the tail offset (never the whole
  file), keeping resource usage minimal.
- Error keywords are aligned with the ACTUAL log levels produced by the
  engines (Xray ``loglevel: warning``, sing-box ``log.level: warn``), so the
  monitor only reacts to real failures, not debug/info noise.
- DNS fallback lines are WARNINGS (not failures) and never trigger alerts.
- Callbacks run on a separate thread to avoid blocking the monitor loop.
"""

import os
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional

from loguru import logger

from src.core.constants import SINGBOX_LOG_FILE, XRAY_LOG_FILE
from src.services.monitoring.signals import CORE_SINGBOX, CORE_XRAY, signal_payload


class PassiveLogMonitor:
    """
    Monitors core engine logs for connection health.

    Features:
    - Tails multiple log files (Xray + sing-box) with a single thread
    - Handles rotation/recreation on Windows and Unix
    - Detects specific error keywords aligned with warning-level logging
    - Debounces alerts to prevent flooding
    - Runs callbacks in separate threads to avoid blocking
    """

    # Error keywords that indicate connection failure (lowercase).
    # Aligned with Xray ``loglevel: warning`` / sing-box ``log.level: warn``.
    # Xray-core (warning level) actually emits these:
    ERROR_KEYWORDS = [
        # --- Xray-core transport / dial errors (warning level) ---
        "failed to handler mux client connection",
        "transport closed",
        "connection reset by peer",
        "connection refused",
        "connection timed out",
        "read timeout",
        "i/o timeout",
        "dial tcp",  # catches "dial tcp ... timeout" and "dial tcp ... refused"
        "handshake failed",
        "all retry attempts failed",
        "no such host",
        "no route to host",
        "network is unreachable",
        "generic::error",
        # --- sing-box TUN engine errors (warn level) ---
        # NOTE: bare "fatal" is deliberately NOT a keyword — it matches config
        # lines such as ``log.level: "fatal"`` and would cause spurious
        # reconnect signals. Real sing-box fatal failures always carry a
        # ``fatal:`` prefix (e.g. ``fatal: failed to create tun``) or appear
        # alongside engine-failure context ("failed to start").
        "fatal:",
        "panic",
        "failed to start",
        "error creating",
        "permission denied",
        "address already in use",
        "no such device",
        "interface not found",
        # Windows-specific sing-box TUN errors
        "wintun",
        "tun adapter",
        "failed to create tun",
    ]

    # Keywords indicating the primary (server-side / remote) DNS resolver failed
    # and Xray is falling back to the secondary remote DNS. These are WARNINGS,
    # not connection failures — they must NOT trigger the failure callback.
    DNS_FALLBACK_KEYWORDS = [
        "failed to resolve domain",
        "failed to lookup ip",
        "dns fallback triggered",
        "dns server failed",
    ]

    # Dial-type keywords whose matched line is checked against the
    # private/LAN-address guard (_is_private_target) BEFORE an alert fires.
    # A dial failure to an INTERNAL address (e.g. ``dial tcp 172.16.0.2:1688:
    # i/o timeout``) means a local service is unreachable — NOT a VPN path
    # failure — so it must never raise PASSIVE_FAILURE. The same keywords
    # against a PUBLIC target remain genuine VPN-connectivity failures.
    DIAL_TARGET_KEYWORDS = [
        "dial tcp",
        "dial udp",
        "i/o timeout",
        "connection refused",
        "connection reset by peer",
        "connection timed out",
    ]

    # RFC 1918 + loopback + link-local + CGNAT + reserved ranges. These are
    # internal-dial markers; a failure against them is a LAN/service issue,
    # not a VPN path failure. The lookaround boundaries require a WHOLE
    # dotted token: a private-looking run inside a longer numeric sequence
    # (e.g. the "192.168.1.5" inside "1.2.192.168.1.5") does not count.
    PRIVATE_IPV4_RE = re.compile(
        r"(?<![\d.])(?P<ip>"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|127\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|169\.254\.\d{1,3}\.\d{1,3}"
        r"|100\.(?:6[4-9]|[7-9]\d)\.\d{1,3}\.\d{1,3}"
        r")(?![\d.])"
    )

    # Configuration
    CHECK_INTERVAL = 1.0  # seconds between log checks
    DEBOUNCE_SECONDS = 5.0  # Minimum time between alerts
    MAX_COOLDOWN_SECONDS = 300.0  # 5 minutes max
    BASE_COOLDOWN_SECONDS = 5.0
    # FP guard: consecutive-match threshold before an alert fires. Default 1
    # (alert on first match — keeps legacy single-line semantics for embedders
    # and tests). Production wiring (ConnectionMonitoringService) raises this
    # to 3 so transient one-off dial errors never trigger a reconnect while a
    # real path outage (which repeats every request) still fires within ~2s.
    REQUIRED_FAILURE_LINES = 1

    def __init__(
        self,
        on_failure_callback: Callable[[dict], None] = None,
        log_files: Optional[List[str]] = None,
    ):
        """
        Initialize the monitor.

        Args:
            on_failure_callback: Function to call when connection failure is
                detected. Receives a payload dict with ``source``.
            log_files: Optional list of log file paths to tail. Defaults to
                the Xray-core and sing-box TUN logs.
        """
        self._on_failure = on_failure_callback
        # Default: tail BOTH cores (Xray proxy + sing-box TUN engine)
        self._log_files = log_files or [XRAY_LOG_FILE, SINGBOX_LOG_FILE]
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Per-file tail state: {path: {"file": handle, "pos": int, "ctime": float|None, "inode": int|None}}
        self._tail_state: dict = {}

        # Single bounded executor for failure callbacks (max 1 worker — one
        # callback at a time; no unbounded daemon thread spawning per alert).
        self._callback_executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="PassiveLogMonitor-Callback"
        )

        # State
        self._last_alert_times: dict = {}  # per-source debounce timestamps
        self._paused = False
        self._paused_until = 0.0
        self._consecutive_failures = 0
        self._last_error_time = 0.0  # For cross-signal validation
        self._last_dns_warn_time = 0.0  # Debounce for DNS fallback warnings
        # FP guard: sliding-window failure tracking per source.
        # Tracks timestamps of failures within FAILURE_WINDOW_SECONDS (12s).
        self._failure_windows: dict = {}  # {source: deque[float]}
        self.FAILURE_WINDOW_SECONDS = 12.0  # 10-15s sliding window
        self.FAILURE_STREAK_WINDOW = self.FAILURE_WINDOW_SECONDS  # backward-compat attribute
        self._pending_failures: dict = {}  # backward-compat alias

    def has_recent_error(self, window_seconds: float = 30.0) -> bool:
        """
        Check if a core error was detected within the time window.

        Used by ActiveConnectivityMonitor for cross-signal validation.

        Args:
            window_seconds: Time window to check for recent errors

        Returns:
            True if an error was detected within the window
        """
        if self._last_error_time == 0.0:
            return False
        return (time.time() - self._last_error_time) < window_seconds

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the monitoring thread."""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._consecutive_failures = 0
            self._stop_event.clear()
            self._tail_state.clear()
            # Recreate the callback executor if a previous stop() shut it down
            # (supports start → stop → start on the same instance).
            if self._callback_executor._shutdown:
                self._callback_executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="PassiveLogMonitor-Callback"
                )

            # Pre-open the log files synchronously (before the thread starts)
            # so the tail offset is captured NOW. Any line written AFTER
            # start() returns is guaranteed to be read by the tailer — a line
            # written in the tiny window before the daemon thread's first tick
            # would otherwise be skipped (the file would be opened at END and
            # the new line already past the offset).
            for log_file in self._log_files:
                self._open_file(log_file)

            self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="PassiveLogMonitor")
            self._thread.start()
            logger.info(f"[PassiveLogMonitor] Started monitoring: {self._log_files}")

    def stop(self):
        """Stop the monitoring thread."""
        with self._lock:
            if not self._running:
                return

            self._running = False
            self._stop_event.set()

            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)

            self._thread = None
            self._tail_state.clear()
            # Shut down the callback executor (wait briefly for in-flight callbacks).
            self._callback_executor.shutdown(wait=False)
            logger.info("[PassiveLogMonitor] Stopped monitoring")

    # ------------------------------------------------------------------
    # Pause / resume (backoff)
    # ------------------------------------------------------------------

    def pause(self, duration: float = 0):
        """
        Pause monitoring.

        Args:
            duration: If > 0, pause for this many seconds. If 0, pause indefinitely until resume().
        """
        if duration > 0:
            self._paused_until = time.time() + duration
            logger.debug(f"[PassiveLogMonitor] Pausing for {duration}s")
        else:
            self._paused = True
            logger.debug("[PassiveLogMonitor] Paused indefinitely")

    def resume(self):
        """Resume monitoring immediately."""
        self._paused = False
        self._paused_until = 0
        self._last_alert_times.clear()  # Reset per-source debounce so a new alert can fire
        self._last_alert_time = 0.0  # Backward-compat alias
        logger.debug("[PassiveLogMonitor] Resumed")

    # ------------------------------------------------------------------
    # Main loop (single thread, multiple files)
    # ------------------------------------------------------------------

    def _monitor_loop(self):
        """Main monitoring loop — one thread tails ALL configured log files."""
        try:
            while not self._stop_event.is_set():
                # 1. Check pause state
                if self._paused:
                    time.sleep(self.CHECK_INTERVAL)
                    continue

                if self._paused_until > 0:
                    if time.time() < self._paused_until:
                        time.sleep(self.CHECK_INTERVAL)
                        continue
                    else:
                        self._paused_until = 0
                        logger.debug("[PassiveLogMonitor] Pause duration expired, resuming")

                # 2. Read new lines from every file (only the new bytes)
                for log_file in self._log_files:
                    if self._stop_event.is_set():
                        break
                    try:
                        self._tail_file(log_file)
                    except Exception as e:
                        logger.error(f"[PassiveLogMonitor] Error reading {log_file}: {e}")

                time.sleep(self.CHECK_INTERVAL)

        finally:
            # Close any open handles
            for state in self._tail_state.values():
                try:
                    if state.get("file"):
                        state["file"].close()
                except Exception:
                    pass
            self._tail_state.clear()

    def _open_file(self, file_path: str):
        """Open a log file and record its tail offset (at END by default).

        Used by ``start()`` to capture the offset synchronously and by
        ``_tail_file`` to (re)open after rotation/truncation.
        """
        if not os.path.exists(file_path):
            return None
        try:
            stat = os.stat(file_path)
            current_inode = stat.st_ino if os.name != "nt" else 0
            current_ctime = stat.st_ctime if os.name == "nt" else 0
            f = open(file_path, "r", encoding="utf-8", errors="ignore")
            f.seek(0, os.SEEK_END)
            self._tail_state[file_path] = {
                "file": f,
                "pos": f.tell(),
                "ctime": current_ctime,
                "inode": current_inode,
            }
            logger.debug(f"[PassiveLogMonitor] Opened log file: {file_path}")
            return f
        except Exception as e:
            logger.warning(f"[PassiveLogMonitor] Could not open {file_path}: {e}")
            return None

    def _tail_file(self, file_path: str):
        """Read and process ONLY the new bytes appended to one log file."""
        state = self._tail_state.get(file_path)

        # File missing → drop state, wait for it to appear
        if not os.path.exists(file_path):
            if state and state.get("file"):
                try:
                    state["file"].close()
                except Exception:
                    pass
                self._tail_state.pop(file_path, None)
            return

        stat = os.stat(file_path)
        current_inode = stat.st_ino if os.name != "nt" else 0
        current_size = stat.st_size
        current_ctime = stat.st_ctime if os.name == "nt" else 0

        # Enforce 5 MB ceiling in real time while subprocess streams logs
        from src.core.constants import LOG_MAX_BYTES
        from src.utils.process_utils import truncate_log_file_inplace

        if current_size >= LOG_MAX_BYTES:
            if state and state.get("file"):
                try:
                    state["file"].close()
                except Exception:
                    pass
                self._tail_state.pop(file_path, None)
            truncate_log_file_inplace(file_path, max_bytes=LOG_MAX_BYTES)
            # After truncation, reopen and seek to end (new content only)
            try:
                f = open(file_path, "r", encoding="utf-8", errors="ignore")
                f.seek(0, os.SEEK_END)
                self._tail_state[file_path] = {
                    "file": f,
                    "pos": f.tell(),
                    "ctime": current_ctime,
                    "inode": current_inode,
                }
            except Exception as e:
                logger.warning(f"[PassiveLogMonitor] Failed to reopen {file_path} after truncation: {e}")
            return

        # First time opening this file (e.g. created after start())
        if state is None:
            self._open_file(file_path)
            return

        # Rotation check (inode changed, size shrunk, or ctime changed on Windows)
        old_pos = state.get("pos", 0)
        old_ctime = state.get("ctime")
        old_inode = state.get("inode")
        if self._is_file_rotated(old_inode, current_inode, old_pos, current_size, old_ctime, current_ctime):
            logger.debug(f"[PassiveLogMonitor] Log rotation detected for {file_path}, reopening")
            try:
                state["file"].close()
            except Exception:
                pass
            try:
                f = open(file_path, "r", encoding="utf-8", errors="ignore")
                f.seek(0, os.SEEK_SET)  # Read the new (rotated) file from the start
                self._tail_state[file_path] = {
                    "file": f,
                    "pos": f.tell(),
                    "ctime": current_ctime,
                    "inode": current_inode,
                }
            except Exception as e:
                logger.warning(f"[PassiveLogMonitor] Failed to reopen {file_path} after rotation: {e}")
                self._tail_state.pop(file_path, None)
            return

        # Read new bytes only (from the last offset)
        try:
            f = state["file"]
            f.seek(old_pos)
            lines = f.readlines()
            new_pos = f.tell()
            state["pos"] = new_pos
            state["ctime"] = current_ctime
            state["inode"] = current_inode

            for line in lines:
                if self._stop_event.is_set():
                    break
                # Derive the core source from the log file name so the signal
                # payload carries 'xray' | 'singbox' (not the full path).
                source = self._source_for_file(file_path)
                self._process_line(line, source)
        except Exception as e:
            logger.debug(f"[PassiveLogMonitor] Read error for {file_path}: {e}")

    def _source_for_file(self, file_path: str) -> str:
        """Map a log file path to its core source name ('xray' | 'singbox')."""
        name = os.path.basename(file_path).lower()
        if "singbox" in name or "sing-box" in name:
            return CORE_SINGBOX
        return CORE_XRAY

    def _is_file_rotated(self, old_inode, new_inode, old_pos, new_size, old_ctime, new_ctime) -> bool:
        """Check if the log file has been rotated."""
        # Unix: inode changed
        if os.name != "nt" and old_inode != new_inode:
            return True
        # Size shrunk (file was recreated)
        if new_size < old_pos:
            return True
        # Windows: creation time changed
        if os.name == "nt" and old_ctime and new_ctime and old_ctime != new_ctime:
            return True
        return False

    # ------------------------------------------------------------------
    # Line processing
    # ------------------------------------------------------------------

    def _reset_failure_streak(self, source: str) -> None:
        """Clear the failure window for ``source`` (e.g. on manual recovery)."""
        with self._lock:
            if source in self._failure_windows:
                self._failure_windows[source].clear()
            self._pending_failures.pop(source, None)

    def _record_failure_candidate(self, log_line: str, source: str) -> bool:
        """Sliding-window failure accumulator.

        Returns True when REQUIRED_FAILURE_LINES occur within FAILURE_WINDOW_SECONDS (12s).
        Non-critical/healthy lines do NOT clear the window; old timestamps naturally expire.
        """
        now = time.time()
        with self._lock:
            if source not in self._failure_windows:
                self._failure_windows[source] = deque()
            window = self._failure_windows[source]

            # If tests or external callers artificially modified _pending_failures, sync window
            if source in self._pending_failures:
                entry = self._pending_failures[source]
                if (now - entry.get("first_seen", now)) > self.FAILURE_WINDOW_SECONDS:
                    window.clear()

            # Prune timestamps outside the sliding window
            while window and (now - window[0]) > self.FAILURE_WINDOW_SECONDS:
                window.popleft()

            window.append(now)
            self._last_error_time = now  # keep cross-signal validation fresh

            # Maintain _pending_failures dict for backward-compatibility
            self._pending_failures[source] = {
                "count": len(window),
                "first_seen": window[0],
            }

            if len(window) >= self.REQUIRED_FAILURE_LINES:
                window.clear()
                self._pending_failures.pop(source, None)
                return True

            logger.debug(
                f"[PassiveLogMonitor] Failure candidate {len(window)}/"
                f"{self.REQUIRED_FAILURE_LINES} ({source}) within {self.FAILURE_WINDOW_SECONDS}s window"
            )
            return False

    def _process_line(self, line: str, source: str = CORE_XRAY):
        """Process a single log line from a given core log."""
        lower_line = line.lower()

        # DNS fallback is a WARNING, not a connection failure. Handle it first so
        # these lines never trigger the failure callback / reconnect flow.
        for keyword in self.DNS_FALLBACK_KEYWORDS:
            if keyword in lower_line:
                domain = self._extract_domain(line)
                self._log_dns_fallback(domain)
                return

        for keyword in self.ERROR_KEYWORDS:
            if keyword in lower_line:
                # C1: private/LAN-address guard — a dial/timeout failure against
                # an INTERNAL address (10.x, 172.16-31.x, 192.168.x, 127.x,
                # 169.254.x, 100.64/10 CGNAT) is a local-service outage, NOT a
                # VPN path failure. Skip the alert so LAN-internal dials never
                # raise PASSIVE_FAILURE. Guard only dial-type keywords: they
                # carry an explicit target, while other keywords (fatal:,
                # failed to start, ...) are engine failures with no target.
                if keyword in self.DIAL_TARGET_KEYWORDS:
                    # C1: private/LAN-address guard — a dial/timeout failure
                    # against an INTERNAL address is a local-service outage,
                    # NOT a VPN path failure.
                    if self._is_private_target(line):
                        logger.debug(
                            f"[PassiveLogMonitor] Keyword '{keyword}' matched but target is "
                            "private/LAN — skipping alert (internal dial, not a VPN path failure)"
                        )
                        break
                    # C1b: direct-outbound guard — traffic that never entered
                    # the VPN tunnel (using outbound/direct) failing is a
                    # direct-path/censorship issue, NOT a tunnel outage.
                    if self._is_direct_outbound(line):
                        logger.debug(
                            f"[PassiveLogMonitor] Keyword '{keyword}' matched but traffic is "
                            "via outbound/direct — skipping alert (direct path, not VPN tunnel)"
                        )
                        break
                logger.debug(f"[PassiveLogMonitor] Keyword '{keyword}' matched in {source} log")
                if self._record_failure_candidate(line.strip(), source):
                    self._trigger_alert(line.strip(), source)
                break
        else:
            # Non-error log line: do NOT reset sliding window (normal traffic
            # interleaved with failure lines must not suppress genuine outages).
            pass

    @staticmethod
    def _is_private_target(line: str) -> bool:
        """Return True if ``line`` contains a private/LAN/reserved IPv4 target.

        Guards dial-type keywords (``dial tcp``, ``i/o timeout``, ...) against
        false PASSIVE_FAILURE pulses: a failure to an internal address means a
        local service is unreachable, not that the VPN path is down.

        Covers RFC 1918 (10/8, 172.16/12, 192.168/16), loopback (127/8),
        link-local (169.254/16) and CGNAT (100.64/10). Matches whole IPv4
        tokens only (preceded/followed by whitespace, ':' or '.'), so e.g.
        ``1.2.3.4`` inside ``192.168.1.5`` cannot leak through.
        """
        return PassiveLogMonitor.PRIVATE_IPV4_RE.search(line) is not None

    @staticmethod
    def _is_direct_outbound(line: str) -> bool:
        """Return True if ``line`` indicates traffic via the DIRECT outbound.

        sing-box logs lines like::

            connection: open connection to 149.154.167.220:443 using outbound/direct[direct]: ...

        ``outbound/direct`` means the traffic went STRAIGHT to the internet —
        it never entered the VPN tunnel. A timeout/refused there is a failure
        of the direct path (censorship/network), NOT a VPN tunnel outage, so
        it must not raise PASSIVE_FAILURE. Guard only dial-type keywords.
        """
        return "outbound/direct" in line.lower()

    def _log_dns_fallback(self, domain: str):
        """Log a warning when primary/server-side DNS resolution fails."""
        now = time.time()
        if now - self._last_dns_warn_time < self.DEBOUNCE_SECONDS:
            return
        self._last_dns_warn_time = now

        subject = domain if domain else "a domain"
        logger.warning(
            f"[DNS Warning] Remote server DNS failed for domain {subject}. Falling back to secondary Remote DNS."
        )

    @staticmethod
    def _extract_domain(line: str) -> str:
        """Extract a hostname from a log line, e.g. 'example.com'."""
        pattern = (
            r"\b([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
            r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?){1,})\b"
        )
        match = re.search(pattern, line)
        return match.group(0) if match else ""

    def _trigger_alert(self, log_line: str, source: str = CORE_XRAY):
        """Trigger an alert if debounce/cooldown allows."""
        now = time.time()

        # Debounce check (per-source, so one core's error never suppresses the
        # other core's alert within the debounce window)
        last_alert = self._last_alert_times.get(source, 0.0)
        if now - last_alert < self.DEBOUNCE_SECONDS:
            return

        logger.warning(f"[PassiveLogMonitor] Connection failure detected ({source}): {log_line}")
        self._last_alert_times[source] = now
        self._last_error_time = now  # For cross-signal validation
        self._consecutive_failures += 1

        # NOTE (F6): no self-pause/backoff here. The per-source debounce above
        # is the duplicate-signal guard; ALL reconnect backoff is owned by
        # AutoReconnectService (5s→300s + cap). Self-pausing would blind this
        # monitor to NEW failures during the backoff window — in proxy mode
        # (no active probe) that could leave zero reconnect signals for minutes.

        # Run callback via the shared bounded executor (single worker, so
        # callbacks serialize instead of spawning unbounded daemon threads).
        if self._on_failure:
            payload = signal_payload(source, line=log_line)
            try:
                self._callback_executor.submit(self._run_callback_safe, payload)
            except RuntimeError:
                # Executor shut down (stop() raced an in-flight alert) — drop.
                logger.debug("[PassiveLogMonitor] Dropped alert (callback executor shut down)")

    def _run_callback_safe(self, payload: dict):
        """Run the failure callback safely in a separate thread."""
        # Check if still running before executing callback
        # This prevents late callbacks after stop()
        with self._lock:
            if not self._running:
                logger.debug("[PassiveLogMonitor] Suppressed callback (stopped)")
                return
        try:
            self._on_failure(payload)
        except Exception as e:
            logger.error(f"[PassiveLogMonitor] Error in failure callback: {e}")
