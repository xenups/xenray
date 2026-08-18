# XenRay Monitoring + Auto-Reconnect — Code Review Findings

Reviewed: passive_log_monitor.py, active_connectivity_monitor.py, auto_reconnect_service.py, service.py, signals.py, connection_manager.py, settings_repository.py, auto_reconnect_toggle_row.py, tests, constants, network_utils, process_utils, ping_service.

---

## 1. Backoff Logic

**[F1] LOW — No jitter in backoff**
auto_reconnect_service.py:113–118. Pure exponential 5→10→20→…→300. Desktop app, so thundering-herd isn't a real problem, but if a second instance were launched it'd reconnect in lockstep.
*Fix:* Add ±20 % jitter: `base * (2 ** n) * random.uniform(0.8, 1.2)`

**[F2] LOW — Backoff resets on reconnect (correct)**
auto_reconnect_service.py:288. `_consecutive_failures = 0` on success; `start_session()` resets both counters. Verified correct.

## 2. Session Semantics

**[F3] MEDIUM — Signal session_id not checked in ConnectionManager._handle_signal**
connection_manager.py:112–120. The guard only checks `self._session_id > 0` — it never compares the signal's originating session. A stale signal from session N+1 that's still in-flight can match the guard for session N+1. In practice the window is tiny and the signal carries no stale-payload risk (only `source: str`), so it's benign-but-sloppy.
*Fix:* Store session_id in the signal payload at `service.py:110` and check it in `_handle_signal`.

## 3. Passive Log Monitor

**[F4] HIGH — "fatal" keyword causes false-positive reconnection**
passive_log_monitor.py:63. `ERROR_KEYWORDS` contains `"fatal"` which matches any line containing that substring, e.g. `log.level: "fatal"` (a config line) or `fatal: log level set to warn`. This can trigger spurious reconnects.
*Fix:* Replace `"fatal"` with `"level: fatal"` or a two-stage check that excludes config/log-level lines.

**[F5] MEDIUM — Resume attribute typo (`_last_alert_time` vs `_last_alert_times`)**
passive_log_monitor.py:208. `resume()` sets `self._last_alert_time = 0.0` — a phantom attribute. The dict is `self._last_alert_times`. Harmless (dead code), but confusing. The line is unreachable anyway since `resume()` is only called in tests.
*Fix:* Delete the line, or change to `self._last_alert_times.clear()` (already done on L207, so just remove L208).

**[F6] MEDIUM — Passive monitor backoff pauses (5–300s) blind it to new failures during reconnect window**
passive_log_monitor.py:460. After the first failure the monitor self-pauses for backoff (5s, then 10s, 20s…up to 300s). During this pause it cannot detect a new failure in the logs. Meanwhile auto_reconnect_service has its own backoff. The result: in a sustained outage, the passive monitor can be paused for up to 5 minutes, suppressing all PASSIVE_FAILURE signals and leaving only the active probe to trigger reconnection. If the active probe also isn't running (proxy mode), there's NO reconnect signal at all.
*Fix:* Either (a) make `_trigger_alert` NOT self-pause — let auto_reconnect_service own all backoff, or (b) call `resume()` from `_attempt_reconnect` when the reconnect attempt completes (success or failure).

**[F7] LOW — `_check_core_recovered` doesn't validate session**
auto_reconnect_service.py:228–240. Called inside `handle_failure` under its own session check, so functionally safe, but any future refactor that calls it independently would be vulnerable.
*Fix:* Add `self._validate_session(session_id, "recovery_check")` at the top.

## 4. Active Monitor

**[F8] MEDIUM — curl absent → `check_proxy_connectivity` returns True (connectivity never lost)**
network_utils.py:71. When `curl` isn't on PATH, `check_proxy_connectivity()` returns `True`. The heavy probe therefore always "succeeds", meaning the active monitor's LOST event never fires in degraded/proxy-OK scenarios. A stale SOCKS port (engine dead but OS hasn't reclaimed the socket) would never be caught by the heavy probe.
*Fix:* Return `False` when curl is missing (fail-closed), or fall back to a Python `urllib` + SOCKS implementation.

**[F9] LOW — `socket.setdefaulttimeout()` pollutes global state**
network_utils.py:33. `check_internet_connection()` calls `socket.setdefaulttimeout(timeout)` inside a retry loop. This is a process-global side effect that could affect other socket operations in other threads.
*Fix:* Use `s.settimeout(timeout)` on the individual socket instead of the global default.

## 5. Resource Usage

**[F10] LOW — Callback threads are fire-and-forget daemons (no cap)**
passive_log_monitor.py:465–470, active_connectivity_monitor.py:281–283. Every alert spawns a new daemon thread. Under rapid failure detection, many threads could accumulate (mitigated by debounce/pause, but still unbounded).
*Fix:* Use a single callback executor thread or `concurrent.futures.ThreadPoolExecutor(max_workers=1)`.

**[F11] LOW — Internet check timeout budget: up to 10.5s**
auto_reconnect_service.py:167–170 → network_utils.py:17 (3 retries × 3s + 2 × 0.5s sleep). Acceptable on a reconnect path but adds latency.
*Fix:* Reduce retries to 2 or timeout to 2s for the reconnect path.

## 6. Default-ON / Toggle Consistency

**[F12] INFO — Default-ON behavior is correct**
settings_repository.py:144. `get_auto_reconnect_enabled()` returns `True` when the file is absent (`val.lower() != "false"` — empty string is not "false"). Toggle UI reads the same method and persists on change. No path causes wrong behavior on a fresh install.

---

## Top 5 Must-Fix

| # | ID  | Severity | Summary |
|---|-----|----------|---------|
| 1 | F4  | HIGH     | **"fatal" keyword false-positives.** Replace with a more specific pattern to avoid triggering spurious reconnections on config/log-level lines. |
| 2 | F6  | MEDIUM   | **Passive monitor self-pause blinds it to failures during reconnect.** Remove the self-pause or have auto-reconnect call `resume()` after each attempt. In proxy mode (no active probe), this can silence all reconnect signals for minutes. |
| 3 | F8  | MEDIUM   | **curl absent → heavy probe always succeeds → connectivity loss never detected.** Return `False` when curl is missing or add a Python fallback. |
| 4 | F10 | LOW      | **Unbounded daemon thread spawning for callbacks.** Use a bounded executor. |
| 5 | F9  | LOW      | **`socket.setdefaulttimeout()` pollutes process-global state.** Use per-socket `.settimeout()`. |
