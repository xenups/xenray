"""Sing-box Metrics Provider - Protocol and adapters for metrics access."""

import json
import time
from dataclasses import dataclass
from typing import Optional, Protocol
from urllib.request import urlopen
from urllib.error import URLError

from loguru import logger


@dataclass
class MetricsSnapshot:
    """Snapshot of sing-box metrics at a point in time."""
    timestamp: float
    uplink_bytes: int
    downlink_bytes: int
    outbound_failures: int
    process_alive: bool


class SingBoxMetricsProvider(Protocol):
    """Protocol for metrics providers - allows switching between API backends."""
    
    def fetch_snapshot(self) -> Optional[MetricsSnapshot]:
        """Fetch current metrics snapshot. Returns None on failure."""
        ...


class ClashAPIProvider:
    """
    Metrics provider using Clash API (experimental.clash_api).
    
    Endpoint: http://127.0.0.1:{port}/traffic
    Returns: {"up": bytes, "down": bytes}
    """
    
    DEFAULT_PORT = 9090
    TIMEOUT = 2.0
    
    def __init__(self, port: int = None):
        self._port = port or self.DEFAULT_PORT
        self._base_url = f"http://127.0.0.1:{self._port}"
    
    def fetch_snapshot(self) -> Optional[MetricsSnapshot]:
        """Fetch metrics from Clash API."""
        try:
            # Get traffic stats
            url = f"{self._base_url}/traffic"
            with urlopen(url, timeout=self.TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
            
            uplink = data.get("up", 0)
            downlink = data.get("down", 0)
            
            # Clash API doesn't expose failure counters directly
            # We infer process alive from successful response
            return MetricsSnapshot(
                timestamp=time.time(),
                uplink_bytes=uplink,
                downlink_bytes=downlink,
                outbound_failures=0,  # Not available in Clash API
                process_alive=True,
            )
            
        except URLError as e:
            logger.debug(f"[ClashAPIProvider] Connection error: {e}")
            return MetricsSnapshot(
                timestamp=time.time(),
                uplink_bytes=0,
                downlink_bytes=0,
                outbound_failures=0,
                process_alive=False,
            )
        except Exception as e:
            logger.warning(f"[ClashAPIProvider] Error fetching metrics: {e}")
            return None


class DebugVarsProvider:
    """
    Metrics provider using Go expvar debug endpoint.
    
    Endpoint: http://127.0.0.1:{port}/debug/vars
    Note: Only available if explicitly enabled in sing-box build.
    """
    
    DEFAULT_PORT = 9090
    TIMEOUT = 2.0
    
    def __init__(self, port: int = None):
        self._port = port or self.DEFAULT_PORT
        self._base_url = f"http://127.0.0.1:{self._port}"
    
    def fetch_snapshot(self) -> Optional[MetricsSnapshot]:
        """Fetch metrics from debug/vars endpoint."""
        try:
            url = f"{self._base_url}/debug/vars"
            with urlopen(url, timeout=self.TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
            
            # Parse expvar format - structure varies by build
            uplink = data.get("outbound_upload_bytes", 0)
            downlink = data.get("outbound_download_bytes", 0)
            failures = data.get("outbound_failures", 0)
            
            return MetricsSnapshot(
                timestamp=time.time(),
                uplink_bytes=uplink,
                downlink_bytes=downlink,
                outbound_failures=failures,
                process_alive=True,
            )
            
        except URLError:
            return MetricsSnapshot(
                timestamp=time.time(),
                uplink_bytes=0,
                downlink_bytes=0,
                outbound_failures=0,
                process_alive=False,
            )
        except Exception as e:
            logger.warning(f"[DebugVarsProvider] Error: {e}")
            return None


class TrafficFileProvider:
    """
    Fallback provider that monitors sing-box log for traffic indicators.
    
    Used when API endpoints are not available.
    Monitors: process alive status via PID check.
    """
    
    def __init__(self, pid_getter=None):
        """
        Args:
            pid_getter: Callable that returns current sing-box PID or None
        """
        self._pid_getter = pid_getter
        self._last_bytes = 0
    
    def fetch_snapshot(self) -> Optional[MetricsSnapshot]:
        """Check if process is alive via PID."""
        import psutil
        
        try:
            pid = self._pid_getter() if self._pid_getter else None
            process_alive = False
            
            if pid:
                try:
                    proc = psutil.Process(pid)
                    process_alive = proc.is_running()
                except psutil.NoSuchProcess:
                    pass
            
            return MetricsSnapshot(
                timestamp=time.time(),
                uplink_bytes=0,
                downlink_bytes=0,
                outbound_failures=0,
                process_alive=process_alive,
            )
            
        except Exception as e:
            logger.warning(f"[TrafficFileProvider] Error: {e}")
            return None
