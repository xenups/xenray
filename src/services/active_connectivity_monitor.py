"""Active Connectivity Monitor - Metrics-based connectivity detection with smart stall detection."""

import threading
import time
from typing import Callable, Optional

from loguru import logger

from src.services.singbox_metrics_provider import MetricsSnapshot, SingBoxMetricsProvider


class ActiveConnectivityMonitor:
    """
    Monitors connectivity using sing-box metrics with smart stall detection.
    
    Detection Logic (ALL must be true):
    1. sing-box process is running
    2. Traffic delta < MIN_TRAFFIC_THRESHOLD for ≥ N samples (~6-9 seconds)
    
    Key Insight: "Traffic is not truly flowing — it is only retry noise."
    Small deltas (< 500 bytes) are TCP retries, not real traffic.
    
    Xray confirmation is optional/confirmatory, not blocking.
    """
    
    SAMPLE_INTERVAL = 3.0         # seconds between samples
    REQUIRED_SAMPLES = 2          # consecutive samples for fast detection (~6s)
    WARNING_SAMPLES = 3           # show warning in UI after this many stalls (~9s)
    MAX_STALL_SAMPLES = 6         # failsafe: trigger after this many (~18s)
    MIN_TRAFFIC_THRESHOLD = 500   # bytes - below this is considered "stalled"
    
    def __init__(
        self,
        metrics_provider: SingBoxMetricsProvider,
        on_connectivity_lost: Optional[Callable[[], None]] = None,
        on_connectivity_restored: Optional[Callable[[], None]] = None,
        on_connectivity_degraded: Optional[Callable[[], None]] = None,
        xray_error_checker: Optional[Callable[[], bool]] = None,
    ):
        """
        Initialize the monitor.
        
        Args:
            metrics_provider: Provider implementing SingBoxMetricsProvider protocol
            on_connectivity_lost: Callback when connectivity is lost
            on_connectivity_restored: Callback when connectivity is restored
            on_connectivity_degraded: Callback when connection shows issues (soft warning)
            xray_error_checker: Optional callback for Xray error confirmation
        """
        self._provider = metrics_provider
        self._on_lost = on_connectivity_lost
        self._on_restored = on_connectivity_restored
        self._on_degraded = on_connectivity_degraded
        self._xray_error_checker = xray_error_checker
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        # State
        self._last_snapshot: Optional[MetricsSnapshot] = None
        self._stall_samples = 0
        self._is_connected = True
        self._warning_emitted = False  # Track if warning already shown
    
    def start(self):
        """Start the monitoring thread."""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            self._stall_samples = 0
            self._is_connected = True
            self._stop_event.clear()
            
            self._thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="ActiveConnectivityMonitor"
            )
            self._thread.start()
            logger.info(
                f"[ActiveConnectivityMonitor] Started (threshold={self.MIN_TRAFFIC_THRESHOLD}b, "
                f"fast={self.REQUIRED_SAMPLES}, failsafe={self.MAX_STALL_SAMPLES})"
            )
    
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
        """Check connectivity using hybrid escalation."""
        snapshot = self._provider.fetch_snapshot()
        
        if snapshot is None:
            logger.warning("[ActiveConnectivityMonitor] Failed to fetch snapshot")
            return
        
        # Evaluate stall condition
        is_stalled = self._evaluate_stall_condition(snapshot)
        
        if is_stalled:
            self._stall_samples += 1
            
            # Check Xray confirmation
            has_xray_errors = False
            if self._xray_error_checker:
                has_xray_errors = self._xray_error_checker()
            
            logger.debug(
                f"[ActiveConnectivityMonitor] Stall detected "
                f"({self._stall_samples}/{self.REQUIRED_SAMPLES}) "
                f"[Xray: {'confirmed' if has_xray_errors else 'waiting'}]"
            )
            
            # Soft warning: show UI feedback after WARNING_SAMPLES
            if self._stall_samples == self.WARNING_SAMPLES and not self._warning_emitted:
                self._warning_emitted = True
                logger.info("[ActiveConnectivityMonitor] Connection degraded - showing warning")
                self._emit_degraded()
            
            # HYBRID ESCALATION:
            # 1. Fast path: stall + Xray confirmation → immediate trigger
            # 2. Failsafe: extended stall without traffic → trigger anyway
            should_trigger = False
            trigger_reason = ""
            
            if self._stall_samples >= self.REQUIRED_SAMPLES and has_xray_errors:
                should_trigger = True
                trigger_reason = "confirmed by Xray"
            elif self._stall_samples >= self.MAX_STALL_SAMPLES:
                should_trigger = True
                trigger_reason = f"failsafe after {self.MAX_STALL_SAMPLES} samples"
            
            if should_trigger and self._is_connected:
                self._is_connected = False
                logger.warning(f"[ActiveConnectivityMonitor] Connectivity LOST ({trigger_reason})")
                self._emit_lost()
        else:
            if self._stall_samples > 0:
                logger.debug("[ActiveConnectivityMonitor] Traffic resumed, resetting stall counter")
            self._stall_samples = 0
            self._warning_emitted = False
            
            if not self._is_connected:
                self._is_connected = True
                logger.info("[ActiveConnectivityMonitor] Connectivity RESTORED")
                self._emit_restored()
        
        self._last_snapshot = snapshot
    
    def _evaluate_stall_condition(self, snapshot: MetricsSnapshot) -> bool:
        """
        Evaluate if traffic is stalled using MIN_TRAFFIC_THRESHOLD.
        
        Traffic is considered STALLED if:
        - Process is alive
        - Δ(uplink + downlink) < MIN_TRAFFIC_THRESHOLD
        
        This ignores TCP retries, buffer flushes, and noise.
        """
        # Process must be running
        if not snapshot.process_alive:
            return False
        
        # First sample - can't compare
        if self._last_snapshot is None:
            return False
        
        # Calculate traffic delta
        last_traffic = self._last_snapshot.uplink_bytes + self._last_snapshot.downlink_bytes
        current_traffic = snapshot.uplink_bytes + snapshot.downlink_bytes
        delta = current_traffic - last_traffic
        
        # Stalled if delta is below threshold (retry noise level)
        is_stalled = delta < self.MIN_TRAFFIC_THRESHOLD
        
        if is_stalled:
            logger.debug(
                f"[ActiveConnectivityMonitor] Traffic delta: {delta}b "
                f"(< {self.MIN_TRAFFIC_THRESHOLD}b threshold)"
            )
        
        return is_stalled
    
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
    
    def _emit_degraded(self):
        """Emit connectivity degraded (soft warning) event."""
        if self._on_degraded:
            try:
                threading.Thread(
                    target=self._on_degraded,
                    daemon=True,
                    name="ActiveConnectivityMonitor-DegradedCallback"
                ).start()
            except Exception as e:
                logger.error(f"[ActiveConnectivityMonitor] Error in degraded callback: {e}")
