"""Lightweight connection-trace instrumentation.

Usage::

    trace = ConnectionTrace.start()
    # ... connection work ...
    trace.mark("INTERNET_CHECK_START")
    # ... internet check ...
    trace.mark("INTERNET_CHECK_END")
    # ... more work ...
    trace.mark("VERIFIED")
    trace.summary()

All methods are no-ops when ``trace=None`` is passed through the call chain,
so existing callers see zero behavioural change.
"""

from __future__ import annotations

import time
import uuid
from typing import List, Optional


class ConnectionTrace:
    """Event-timeline recorder for one connection attempt.

    Events are stored as ``(monotonic_offset, event_name)`` tuples and
    printed as a structured log line on each ``mark()`` call.  The final
    ``summary()`` prints a compact table with per-step deltas.
    """

    def __init__(self) -> None:
        self._id: str = uuid.uuid4().hex[:8]
        self._start: float = time.monotonic()
        self._events: List[tuple[float, str]] = []

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def start(cls) -> "ConnectionTrace":
        """Create and begin a new trace."""
        trace = cls()
        trace.mark("CONNECT_CLICK")
        return trace

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def mark(self, event: str) -> None:
        """Record *event* with elapsed time since ``start()``."""
        elapsed = time.monotonic() - self._start
        self._events.append((elapsed, event))
        print(
            f"[TRACE {self._id}] +{elapsed:06.3f}s  {event}",
            flush=True,
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Print a per-step delta table and return the raw timeline dict."""
        evts = self._events
        if not evts:
            print(f"[TRACE {self._id}] (empty)")
            return {"id": self._id, "events": []}

        total = evts[-1][0] - evts[0][0]
        lines: list[str] = []
        lines.append(f"\n=== TRACE {self._id}  ({len(evts)} events, {total:.3f}s total) ===")
        lines.append(f"{'Event':<35s} {'Abs':>8s}  {'Delta':>8s}")
        lines.append("-" * 55)

        prev_t = evts[0][0]
        for t, name in evts:
            delta = t - prev_t
            lines.append(f"{name:<35s} {t:8.3f}s  {delta:+8.3f}s")
            prev_t = t

        lines.append("-" * 55)
        lines.append(f"{'TOTAL (first → last)':<35s} {total:8.3f}s")

        # Convenience buckets
        buckets = self._compute_buckets()
        if buckets:
            lines.append("\nKey intervals:")
            for label, dt in buckets.items():
                lines.append(f"  {label:<35s} {dt:8.3f}s")

        table = "\n".join(lines)
        print(table, flush=True)

        return {"id": self._id, "events": evts, "total": total, "buckets": buckets}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compute_buckets(self) -> dict[str, float]:
        """Compute named intervals from commonly-paired markers."""
        by_name = {name: t for t, name in self._events}
        pairs = [
            ("CLICK → VERIFIED", "CONNECT_CLICK", "VERIFIED"),
            ("CLICK → CONNECTED", "CONNECT_CLICK", "CONNECTED"),
            ("INTERNET_CHECK", "INTERNET_CHECK_START", "INTERNET_CHECK_END"),
            ("PRE_CHECKS", "PRE_CHECKS_START", "PRE_CHECKS_END"),
            ("XRAY_START (orchestrator)", "XRAY_START", "XRAY_READY"),
            ("  orphan_cleanup", "XRAY_ORPHAN_CLEANUP_START", "XRAY_ORPHAN_CLEANUP_END"),
            ("  process_spawn", "XRAY_SPAWN_START", "XRAY_SPAWN_END"),
            ("  sni_spoof", "XRAY_SNI_SPOOF_START", "XRAY_SNI_SPOOF_END"),
            ("  dns_setup", "XRAY_DNS_SETUP_START", "XRAY_DNS_SETUP_END"),
            ("SINGBOX_START (orchestrator)", "SINGBOX_START", "SINGBOX_STARTED"),
            ("  config_build", "SB_CONFIG_BUILD_START", "SB_CONFIG_BUILD_END"),
            ("  wait_xray_ready", "SB_WAIT_XRAY_START", "SB_WAIT_XRAY_END"),
            ("  write+spawn", "SB_WRITE_AND_SPAWN_START", "SB_WRITE_AND_SPAWN_END"),
            ("  wait_tun_ready", "SB_WAIT_TUN_START", "SB_WAIT_TUN_END"),
            ("TUN_PROBE", "TUN_PROBE_START", "TUN_PROBE_END"),
            ("HEALTH_CHECK_total", "HEALTH_CHECK_START", "HEALTH_CHECK_END"),
            ("POST_VERIFIED", "POST_VERIFIED_START", "POST_VERIFIED_END"),
        ]
        result: dict[str, float] = {}
        for label, start_name, end_name in pairs:
            if start_name in by_name and end_name in by_name:
                result[label] = by_name[end_name] - by_name[start_name]
        return result


# Typing alias for the optional parameter in call chains
Trace = Optional[ConnectionTrace]
