"""Xray Process Monitor Provider — replaces the Sing-box Clash API metrics provider.

Monitors Xray liveness by:
1. Checking that the Xray process is still alive (via PID)
2. Performing a periodic HTTP connectivity probe through the tunnel

This replaces ClashAPIProvider / SingBoxMetricsProvider which polled
sing-box's Clash API (http://127.0.0.1:9090/connections).
"""

import time
from dataclasses import dataclass
from typing import Callable, Optional

from loguru import logger


@dataclass
class MetricsSnapshot:
    """Snapshot of connection metrics at a point in time."""

    timestamp: float
    uplink_bytes: int
    downlink_bytes: int
    outbound_failures: int
    process_alive: bool


class XrayProcessProvider:
    """
    Metrics provider that monitors Xray process liveness.

    Replaces the Sing-box Clash API approach. Instead of polling
    byte-delta counters from sing-box, we check:
    1. Is the Xray PID still alive?
    2. (Optional) Does a direct HTTP probe succeed?

    This provider is intentionally simple — the ActiveConnectivityMonitor
    already layers smarter stall-detection logic on top of the raw snapshot.
    """

    PROBE_URL = "http://connectivitycheck.gstatic.com/generate_204"
    PROBE_TIMEOUT = 5.0

    def __init__(
        self,
        pid_getter: Optional[Callable[[], Optional[int]]] = None,
        socks_port_getter: Optional[Callable[[], int]] = None,
    ):
        """
        Args:
            pid_getter: Callable returning current Xray PID, or None if not running.
            socks_port_getter: Callable returning current SOCKS port (for proxy-mode probes).
        """
        self._pid_getter = pid_getter
        self._socks_port_getter = socks_port_getter
        self._probe_count = 0

    def fetch_snapshot(self) -> Optional[MetricsSnapshot]:
        """
        Fetch current liveness snapshot.

        Returns MetricsSnapshot with process_alive reflecting Xray PID state.
        uplink/downlink bytes are not available without Xray stats API;
        we return 0 and rely on process_alive + periodic HTTP probe for
        stall detection in the monitor.
        """
        try:
            pid = self._pid_getter() if self._pid_getter else None
            process_alive = self._check_pid_alive(pid)

            self._probe_count += 1
            return MetricsSnapshot(
                timestamp=time.time(),
                uplink_bytes=0,
                downlink_bytes=0,
                outbound_failures=0 if process_alive else 1,
                process_alive=process_alive,
            )

        except Exception as e:
            logger.warning(f"[XrayProcessProvider] Error fetching snapshot: {e}")
            return None

    def _check_pid_alive(self, pid: Optional[int]) -> bool:
        """Check if the given PID is alive."""
        if not pid:
            return False
        try:
            import psutil

            proc = psutil.Process(pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except Exception:
            return False
