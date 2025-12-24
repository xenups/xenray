"""Active Connectivity Monitor - Metrics-based connectivity detection."""

import threading
import time
from typing import Callable, Optional

from loguru import logger

from src.services.singbox_metrics_provider import MetricsSnapshot, SingBoxMetricsProvider


class ActiveConnectivityMonitor:
    """
    Monitors connectivity using sing-box metrics.
    
    Detects connectivity LOST when ALL conditions are true:
    1. sing-box process is running
    2. outbound failure counter is increasing
    3. uplink + downlink bytes show no delta
    4. conditions hold for ≥ 2 consecutive samples
    
    Emits events via callback, does NOT trigger reconnect directly.
    """
    
    SAMPLE_INTERVAL = 3.0  # seconds between samples
    REQUIRED_SAMPLES = 2   # consecutive samples for detection
    
    def __init__(
        self,
        metrics_provider: SingBoxMetricsProvider,
        on_connectivity_lost: Optional[Callable[[], None]] = None,
        on_connectivity_restored: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize the monitor.
        
        Args:
            metrics_provider: Provider implementing SingBoxMetricsProvider protocol
            on_connectivity_lost: Callback when connectivity is lost
            on_connectivity_restored: Callback when connectivity is restored
        """
        self._provider = metrics_provider
        self._on_lost = on_connectivity_lost
        self._on_restored = on_connectivity_restored
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        # State
        self._last_snapshot: Optional[MetricsSnapshot] = None
        self._consecutive_failure_samples = 0
        self._is_connected = True  # Assume connected at start
    
    def start(self):
        """Start the monitoring thread."""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            self._consecutive_failure_samples = 0
            self._is_connected = True
            self._stop_event.clear()
            
            self._thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="ActiveConnectivityMonitor"
            )
            self._thread.start()
            logger.info("[ActiveConnectivityMonitor] Started")
    
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
            logger.info("[ActiveConnectivityMonitor] Stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        try:
            while not self._stop_event.is_set():
                self._check_connectivity()
                self._stop_event.wait(self.SAMPLE_INTERVAL)
        except Exception as e:
            logger.error(f"[ActiveConnectivityMonitor] Error in monitor loop: {e}")
    
    def _check_connectivity(self):
        """Check connectivity based on metrics snapshot."""
        snapshot = self._provider.fetch_snapshot()
        
        if snapshot is None:
            logger.warning("[ActiveConnectivityMonitor] Failed to fetch snapshot")
            return
        
        is_failure_condition = self._evaluate_failure_condition(snapshot)
        
        if is_failure_condition:
            self._consecutive_failure_samples += 1
            logger.debug(
                f"[ActiveConnectivityMonitor] Failure condition detected "
                f"({self._consecutive_failure_samples}/{self.REQUIRED_SAMPLES})"
            )
            
            if self._consecutive_failure_samples >= self.REQUIRED_SAMPLES:
                if self._is_connected:
                    self._is_connected = False
                    logger.warning("[ActiveConnectivityMonitor] Connectivity LOST")
                    self._emit_lost()
        else:
            if self._consecutive_failure_samples > 0:
                logger.debug("[ActiveConnectivityMonitor] Failure condition cleared")
            self._consecutive_failure_samples = 0
            
            if not self._is_connected:
                self._is_connected = True
                logger.info("[ActiveConnectivityMonitor] Connectivity RESTORED")
                self._emit_restored()
        
        self._last_snapshot = snapshot
    
    def _evaluate_failure_condition(self, snapshot: MetricsSnapshot) -> bool:
        """
        Evaluate if failure conditions are met.
        
        ALL conditions must be true:
        1. Process is running
        2. Failure counter is increasing (compared to last snapshot)
        3. No traffic delta (uplink + downlink unchanged)
        """
        if not snapshot.process_alive:
            # Process dead is a different issue - don't trigger via this path
            return False
        
        if self._last_snapshot is None:
            # First sample, cannot compare
            return False
        
        # Condition 1: Process running
        # Already checked above
        
        # Condition 2: Failure counter increasing
        failures_increased = snapshot.outbound_failures > self._last_snapshot.outbound_failures
        
        # Condition 3: No traffic delta
        last_traffic = self._last_snapshot.uplink_bytes + self._last_snapshot.downlink_bytes
        current_traffic = snapshot.uplink_bytes + snapshot.downlink_bytes
        no_traffic_delta = current_traffic == last_traffic
        
        # All conditions must be true
        return failures_increased and no_traffic_delta
    
    def _emit_lost(self):
        """Emit connectivity lost event."""
        if self._on_lost:
            try:
                threading.Thread(
                    target=self._on_lost,
                    daemon=True,
                    name="ActiveConnectivityMonitor-LostCallback"
                ).start()
            except Exception as e:
                logger.error(f"[ActiveConnectivityMonitor] Error in lost callback: {e}")
    
    def _emit_restored(self):
        """Emit connectivity restored event."""
        if self._on_restored:
            try:
                threading.Thread(
                    target=self._on_restored,
                    daemon=True,
                    name="ActiveConnectivityMonitor-RestoredCallback"
                ).start()
            except Exception as e:
                logger.error(f"[ActiveConnectivityMonitor] Error in restored callback: {e}")
