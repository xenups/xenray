"""
Network Stability Observer - Passive network quality monitoring.

This module provides zero-overhead network quality assessment using passive signals
from existing logs and events. No active probing or polling is performed.

Design principles:
- Passive signals only (no new network traffic)
- Event-driven (no polling loops)
- Thread-safe (RLock for concurrent access)
- Zero impact on VPN stability/latency
"""

import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Optional

from loguru import logger


class NetworkQuality(Enum):
    """Network quality states based on observed error patterns."""

    CRITICAL = 0  # Severe issues, aggressive decrease
    UNSTABLE = 1  # Frequent issues, decrease rate
    DEGRADED = 2  # Some issues, maintain rate
    STABLE = 3  # Normal operation
    EXCELLENT = 4  # No issues, increase rate

    def __lt__(self, other):
        """Enable comparison for hysteresis logic."""
        if isinstance(other, NetworkQuality):
            return self.value < other.value
        return NotImplemented

    def __le__(self, other):
        """Enable comparison for hysteresis logic."""
        if isinstance(other, NetworkQuality):
            return self.value <= other.value
        return NotImplemented

    def __gt__(self, other):
        """Enable comparison for hysteresis logic."""
        if isinstance(other, NetworkQuality):
            return self.value > other.value
        return NotImplemented

    def __ge__(self, other):
        """Enable comparison for hysteresis logic."""
        if isinstance(other, NetworkQuality):
            return self.value >= other.value
        return NotImplemented

    @property
    def name_str(self) -> str:
        """Get the quality name as a string."""
        names = {
            0: "critical",
            1: "unstable",
            2: "degraded",
            3: "stable",
            4: "excellent",
        }
        return names[self.value]


class ErrorSeverity(Enum):
    """Error severity classification to avoid false positives."""

    TRANSIENT = 1  # Single timeout, DNS hiccup (ignored)
    MODERATE = 2  # Connection reset, repeated timeout
    SEVERE = 3  # TLS failure, process crash


class ErrorType(Enum):
    """Types of network errors we track."""

    TIMEOUT = "timeout"
    CONNECTION_RESET = "connection_reset"
    DNS_FAILURE = "dns_failure"
    TLS_FAILURE = "tls_failure"
    PROCESS_CRASH = "process_crash"
    RECONNECT = "reconnect"


@dataclass
class ErrorSignal:
    """Represents a single error event."""

    type: ErrorType
    severity: ErrorSeverity
    timestamp: float = field(default_factory=time.time)


@dataclass
class NetworkMetrics:
    """Rolling window metrics (60-120 seconds)."""

    timeout_count: int = 0
    connection_reset_count: int = 0
    dns_failures: int = 0
    tls_failures: int = 0
    process_crashes: int = 0

    # Handshake timing
    avg_handshake_ms: float = 0.0
    max_handshake_ms: float = 0.0
    handshake_samples: int = 0

    # Reconnection tracking
    reconnect_count: int = 0

    # Error ratio
    total_events: int = 0
    error_events: int = 0

    @property
    def error_ratio(self) -> float:
        """Calculate error ratio."""
        if self.total_events == 0:
            return 0.0
        return self.error_events / self.total_events


class WindowConfig:
    """Adaptive timing window configuration."""

    STABLE_WINDOW = 120  # seconds (stable networks)
    UNSTABLE_WINDOW = 30  # seconds (unstable networks)
    DEFAULT_WINDOW = 60  # seconds (default)

    @staticmethod
    def get_window_size(recent_error_rate: float) -> int:
        """Dynamically adjust window size based on error rate."""
        if recent_error_rate < 0.10:  # < 10% errors (was 5%) - prefer stability
            return WindowConfig.STABLE_WINDOW
        elif recent_error_rate < 0.20:  # 10-20% errors
            return WindowConfig.DEFAULT_WINDOW
        else:  # > 20% errors
            return WindowConfig.UNSTABLE_WINDOW


class AdaptationConfig:
    """Rate adaptation configuration."""

    # Hysteresis: require N consecutive bad/good windows before state change
    DEGRADATION_THRESHOLD = 5  # consecutive bad windows (was 3 - more tolerant)
    RECOVERY_THRESHOLD = 3  # consecutive good windows (was 2) - stricter recovery

    # Max rate change per adjustment
    MAX_RATE_CHANGE = 1.0  # conn/sec

    # State transition thresholds (errors in window) - MUCH LESS SENSITIVE
    DEGRADED_THRESHOLD = 8  # was 3 - require more errors to mark as degraded
    UNSTABLE_THRESHOLD = 15  # was 5 - require many errors to mark as unstable
    CRITICAL_THRESHOLD = 25  # was 10 - only critical if severe issues

    # New stability controls
    CRITICAL_COOLDOWN = 30.0  # Minimum seconds to stay in CRITICAL
    RECOVERY_STEP_LIMIT = 2  # Max levels to jump up during recovery (was 1)

    # Fast-Path Detection - LESS AGGRESSIVE
    FAST_PATH_WINDOW = 3.0  # Check for burst errors in last 3 seconds
    FAST_PATH_THRESHOLD = (
        10  # Immediate CRITICAL if >= 10 errors in fast window (was 5)
    )

    # Silence Detection (Passive Hard Disconnect)
    SILENCE_TIMEOUT = 2.0  # Downgrade if no success symbols for 2s (was 5.0s)
    SILENCE_WARMUP = (
        30.0  # Grace period at startup before silence detection activates (was 15s)
    )


class NetworkStabilityObserver:
    """
    Passive network stability observer.

    Monitors network quality using existing signals without active probing.
    Thread-safe for concurrent event handling.
    """

    # Log pattern matching (multiple patterns per error type)
    TIMEOUT_PATTERNS = [
        r"\[Error\].*timeout",
        r"dial tcp.*i/o timeout",
        r"context deadline exceeded",
        r"operation timed out",
    ]

    CONNECTION_RESET_PATTERNS = [
        r"connection reset by peer",
        r"broken pipe",
        r"connection refused",
        r"connection.*(?:dropped|closed|lost)",  # connection dropped/closed/lost
        r"connection.*error",  # generic connection error
        r"failed to process outbound traffic",
        r"failed to find an available destination",
        r"failed to open connection",
        r"failed to dial",
        r"failed to transfer response payload",
    ]

    DNS_FAILURE_PATTERNS = [
        r"dns.*lookup.*timeout",
        r"no such host",
        r"dns.*failure",
        r"process DNS packet.*bad",  # Captures bad question name/rdata
        r"dns.*bad rdata",
        r"dns: buffer size too small",
        r"dns: message size too large",
        r"dns: exchange failed",  # e.g. "dns: exchange failed for ... IN A: EOF"
    ]

    TLS_FAILURE_PATTERNS = [
        r"tls.*handshake.*timeout",
        r"tls.*handshake.*failed",
        r"certificate.*invalid",
        r"tls: bad record MAC",
        r"tls: bad certificate",
        r"XTLS rejected",
    ]

    SUCCESS_PATTERNS = [
        r"connection established",
        r"connected to",
        r"tunnel.*opened",
        r"handshake completed",
    ]

    def __init__(
        self,
        window_size: int = WindowConfig.DEFAULT_WINDOW,
        adaptive_window: bool = True,
    ):
        """
        Initialize network stability observer.

        Args:
            window_size: Initial sliding window size in seconds
            adaptive_window: Enable adaptive window sizing
        """
        self._lock = threading.RLock()  # Thread-safe

        # Configuration
        self._window_size = window_size
        self._adaptive_window = adaptive_window

        # Current state
        self._current_quality = NetworkQuality.STABLE
        self._metrics = NetworkMetrics()

        # Event history (sliding window)
        self._error_history: Deque[ErrorSignal] = deque()
        self._handshake_history: Deque[
            tuple[float, float]
        ] = deque()  # (timestamp, duration_ms)

        # State transition tracking (hysteresis)
        self._consecutive_bad_windows = 0
        self._consecutive_good_windows = 0

        # Timing
        self._critical_entry_time = 0.0  # Time when we entered CRITICAL state
        self._last_window_update = time.time()
        self._last_evaluation_time = time.time()
        self._stable_duration = 0.0  # How long we've been stable

        # Activity timestamps for Silence Detection
        self._last_success_time = time.time()
        self._last_error_time = 0.0
        self._startup_time = time.time()

        # Callbacks for state changes
        self._state_callbacks = []

        # Optimization: Rolling counters to avoid O(N) scans
        self._rolling_counts = {"moderate_errors": 0, "reconnects": 0, "crashes": 0}

        # Initialize extracted components for better SRP compliance
        from src.services.log_parser import LogParser
        from src.services.quality_evaluator import QualityEvaluator

        self._log_parser = LogParser()
        self._quality_evaluator = QualityEvaluator()
        logger.info("[NetworkObserver] Initialized LogParser and QualityEvaluator")

        logger.info(
            f"[NetworkObserver] Initialized: window={window_size}s, "
            f"adaptive={adaptive_window}"
        )

    def add_callback(self, callback):
        """Register a callback for quality state changes."""
        with self._lock:
            self._state_callbacks.append(callback)

    def on_timeout(self, key: str = "default"):
        """
        Report a timeout event (passive signal).

        Args:
            key: Connection key for tracking
        """
        with self._lock:
            # Classify severity based on recent history
            recent_timeouts = sum(
                1
                for e in self._error_history
                if e.type == ErrorType.TIMEOUT and time.time() - e.timestamp < 30
            )

            severity = (
                ErrorSeverity.TRANSIENT
                if recent_timeouts < 3
                else ErrorSeverity.MODERATE
            )

            self._record_error(ErrorType.TIMEOUT, severity)
            self._evaluate_quality()

    def on_connection_reset(self):
        """Report a connection reset event (passive signal)."""
        with self._lock:
            self._record_error(ErrorType.CONNECTION_RESET, ErrorSeverity.MODERATE)
            self._evaluate_quality()

    def on_dns_failure(self):
        """Report a DNS failure event (passive signal)."""
        with self._lock:
            self._record_error(ErrorType.DNS_FAILURE, ErrorSeverity.MODERATE)
            self._evaluate_quality()

    def on_tls_failure(self):
        """Report a TLS handshake failure (passive signal)."""
        with self._lock:
            self._record_error(ErrorType.TLS_FAILURE, ErrorSeverity.SEVERE)
            self._evaluate_quality()

    def on_process_crash(self):
        """Report a process crash (passive signal)."""
        with self._lock:
            self._record_error(ErrorType.PROCESS_CRASH, ErrorSeverity.SEVERE)
            self._evaluate_quality()

    def on_handshake_complete(self, duration_ms: float):
        """
        Report a successful handshake with timing (passive signal).

        Args:
            duration_ms: Handshake duration in milliseconds
        """
        with self._lock:
            now = time.time()
            self._last_success_time = now
            self._handshake_history.append((now, duration_ms))
            self._update_handshake_metrics()
            self._metrics.total_events += 1

            # Immediately re-evaluate quality to detect reconnection
            self._evaluate_quality()

    def on_connection_success(self):
        """Report a successful connection event (passive signal)."""
        with self._lock:
            self._last_success_time = time.time()
            self._metrics.total_events += 1
            # Immediate evaluation to clear Critical state if previously silent
            self._evaluate_quality()

    def on_reconnect(self):
        """Report a reconnection attempt (passive signal)."""
        with self._lock:
            self._metrics.reconnect_count += 1
            self._record_error(ErrorType.RECONNECT, ErrorSeverity.MODERATE)
            self._evaluate_quality()

    def parse_log_line(self, line: str) -> Optional[ErrorSignal]:
        """
        Parse a log line for error patterns (passive signal extraction).

        Args:
            line: Log line from Xray/Singbox stderr

        Returns:
            ErrorSignal if pattern matched, None otherwise
        """
        # Check timeout patterns
        for pattern in self.TIMEOUT_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                self.on_timeout()
                return ErrorSignal(ErrorType.TIMEOUT, ErrorSeverity.MODERATE)

        # Check connection reset patterns
        for pattern in self.CONNECTION_RESET_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                self.on_connection_reset()
                return ErrorSignal(ErrorType.CONNECTION_RESET, ErrorSeverity.MODERATE)

        # Check DNS failure patterns
        for pattern in self.DNS_FAILURE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                self.on_dns_failure()
                return ErrorSignal(ErrorType.DNS_FAILURE, ErrorSeverity.MODERATE)

        # Check TLS failure patterns
        for pattern in self.TLS_FAILURE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                self.on_tls_failure()
                return ErrorSignal(ErrorType.TLS_FAILURE, ErrorSeverity.SEVERE)

        # Unknown error - log for future pattern updates (DEBUG only)
        if "ERROR" in line and logger.level("DEBUG").no <= logger._core.min_level:
            # Only log in DEBUG mode to avoid spam
            logger.debug(f"[NetworkObserver] Unclassified error: {line.strip()}")

        # Check success patterns
        for pattern in self.SUCCESS_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                self.on_connection_success()
                return None  # Not an error signal

        return None

    def get_quality(self) -> NetworkQuality:
        """Get current network quality state (thread-safe)."""
        with self._lock:
            # Periodically re-evaluate even if no errors occur (to allow recovery)
            if time.time() - self._last_evaluation_time > 5.0:
                self._evaluate_quality()
            return self._current_quality

    def get_metrics(self) -> NetworkMetrics:
        """Get current metrics snapshot (thread-safe)."""
        with self._lock:
            return NetworkMetrics(
                timeout_count=self._metrics.timeout_count,
                connection_reset_count=self._metrics.connection_reset_count,
                dns_failures=self._metrics.dns_failures,
                tls_failures=self._metrics.tls_failures,
                process_crashes=self._metrics.process_crashes,
                avg_handshake_ms=self._metrics.avg_handshake_ms,
                max_handshake_ms=self._metrics.max_handshake_ms,
                handshake_samples=self._metrics.handshake_samples,
                reconnect_count=self._metrics.reconnect_count,
                total_events=self._metrics.total_events,
                error_events=self._metrics.error_events,
            )

    def _record_error(self, error_type: ErrorType, severity: ErrorSeverity):
        """Record an error event (must be called under lock)."""
        signal = ErrorSignal(type=error_type, severity=severity)
        self._error_history.append(signal)

        # Only count MODERATE+ errors
        if severity.value >= ErrorSeverity.MODERATE.value:
            self._last_error_time = time.time()
            self._metrics.error_events += 1

            # Update rolling counters (Optimization)
            self._rolling_counts["moderate_errors"] += 1
            if error_type == ErrorType.RECONNECT:
                self._rolling_counts["reconnects"] += 1
            elif error_type == ErrorType.PROCESS_CRASH:
                self._rolling_counts["crashes"] += 1

            # Update specific counters
            if error_type == ErrorType.TIMEOUT:
                self._metrics.timeout_count += 1
            elif error_type == ErrorType.CONNECTION_RESET:
                self._metrics.connection_reset_count += 1
            elif error_type == ErrorType.DNS_FAILURE:
                self._metrics.dns_failures += 1
            elif error_type == ErrorType.TLS_FAILURE:
                self._metrics.tls_failures += 1
            elif error_type == ErrorType.PROCESS_CRASH:
                self._metrics.process_crashes += 1

        self._metrics.total_events += 1
        self._cleanup_old_events()

    def _update_handshake_metrics(self):
        """Update handshake timing metrics (must be called under lock)."""
        if not self._handshake_history:
            return

        # Calculate average and max from recent samples
        recent_samples = [
            duration
            for ts, duration in self._handshake_history
            if time.time() - ts < self._window_size
        ]

        if recent_samples:
            self._metrics.avg_handshake_ms = sum(recent_samples) / len(recent_samples)
            self._metrics.max_handshake_ms = max(recent_samples)
            self._metrics.handshake_samples = len(recent_samples)

    def _cleanup_old_events(self):
        """Remove events outside the sliding window (must be called under lock)."""
        current_time = time.time()
        cutoff_time = current_time - self._window_size

        # Clean error history and update rolling counters
        while self._error_history and self._error_history[0].timestamp < cutoff_time:
            expired_event = self._error_history.popleft()

            # Decrement counters if event was counted
            if expired_event.severity.value >= ErrorSeverity.MODERATE.value:
                self._rolling_counts["moderate_errors"] -= 1
                if expired_event.type == ErrorType.RECONNECT:
                    self._rolling_counts["reconnects"] -= 1
                elif expired_event.type == ErrorType.PROCESS_CRASH:
                    self._rolling_counts["crashes"] -= 1

        # Clean handshake history
        while self._handshake_history and self._handshake_history[0][0] < cutoff_time:
            self._handshake_history.popleft()

    def _evaluate_quality(self):
        """
        Evaluate network quality based on current metrics (must be called under lock).

        Orchestrates the evaluation pipeline:
        1. Cleanup & Metrics
        2. Fast-Path / Silence Detection
        3. Standard Evaluation (if no override)
        4. Stability Constraints
        5. Hysteresis & Transition
        """
        self._last_evaluation_time = time.time()
        self._cleanup_old_events()

        # 0. Maintenance
        self._adjust_window_size()

        # 1. Gather Metrics
        metrics = self._calculate_window_metrics()

        # 2. Check Overrides (Fast Path / Silence)
        target_quality, bypass_hysteresis, reason = self._check_overrides(metrics)

        # 3. Standard Evaluation (if no override)
        if target_quality is None:
            target_quality = self._determine_base_quality(metrics)
            bypass_hysteresis = False

        # 4. Apply Stability Constraints (Cooldowns, Step Limits)
        target_quality = self._apply_stability_constraints(
            target_quality, bypass_hysteresis
        )

        # 5. Apply Hysteresis & Transition
        self._apply_hysteresis(target_quality, bypass_hysteresis, metrics, reason)

    def _adjust_window_size(self):
        """Adjust sliding window size based on error rate."""
        if self._adaptive_window:
            error_rate = self._metrics.error_ratio
            new_window = WindowConfig.get_window_size(error_rate)
            if new_window != self._window_size:
                self._window_size = new_window
                logger.debug(f"[NetworkObserver] Window size adjusted to {new_window}s")

    def _calculate_window_metrics(self) -> dict:
        """Calculate metrics for the current sliding window (Optimized)."""
        # Ensure counters don't drift negative due to any race/logic bug
        return {
            "moderate_errors": max(0, self._rolling_counts["moderate_errors"]),
            "reconnects": max(0, self._rolling_counts["reconnects"]),
            "crashes": max(0, self._rolling_counts["crashes"]),
            "total_events": len(self._error_history) + len(self._handshake_history),
        }

    def _check_overrides(
        self, metrics: dict
    ) -> tuple[Optional[NetworkQuality], bool, Optional[str]]:
        """
        Check for conditions that override standard logic (Fast-Path, Silence).
        Returns: (TargetQuality, BypassHysteresis, Reason)
        """
        now = time.time()

        # A. Fast-Path Detection (Burst Logic - High Confidence Signals Only)
        high_confidence_types = {
            ErrorType.DNS_FAILURE,
            ErrorType.TIMEOUT,
            ErrorType.TLS_FAILURE,
            ErrorType.PROCESS_CRASH,
        }

        recent_burst_errors = sum(
            1
            for e in self._error_history
            if e.timestamp >= now - AdaptationConfig.FAST_PATH_WINDOW
            and e.type in high_confidence_types
            and e.severity.value >= ErrorSeverity.MODERATE.value
        )

        if recent_burst_errors >= AdaptationConfig.FAST_PATH_THRESHOLD:
            return (
                NetworkQuality.CRITICAL,
                True,
                f"fast-path: {recent_burst_errors} high-conf errors in {AdaptationConfig.FAST_PATH_WINDOW}s",
            )

        # B. Silence Detection (Hard Disconnect / Idle)
        if now - self._startup_time < AdaptationConfig.SILENCE_WARMUP:
            # Skip silence detection during warmup period
            pass
        elif (now - self._last_success_time) > AdaptationConfig.SILENCE_TIMEOUT and (
            now - self._last_error_time
        ) > AdaptationConfig.SILENCE_TIMEOUT:
            return (
                NetworkQuality.CRITICAL,
                True,
                f"silence detection: no activity > {AdaptationConfig.SILENCE_TIMEOUT}s",
            )

        return None, False, None

    def _determine_base_quality(self, metrics: dict) -> NetworkQuality:
        """Determine baseline target quality from window metrics."""
        moderate_errors = metrics["moderate_errors"]
        reconnects = metrics["reconnects"]
        crashes = metrics["crashes"]

        if moderate_errors >= AdaptationConfig.CRITICAL_THRESHOLD or crashes > 0:
            return NetworkQuality.CRITICAL
        elif moderate_errors >= AdaptationConfig.UNSTABLE_THRESHOLD or reconnects >= 3:
            return NetworkQuality.UNSTABLE
        elif moderate_errors >= AdaptationConfig.DEGRADED_THRESHOLD:
            return NetworkQuality.DEGRADED
        elif moderate_errors == 0:
            return NetworkQuality.EXCELLENT
        else:
            return NetworkQuality.STABLE

    def _apply_stability_constraints(
        self, target_quality: NetworkQuality, bypass_hysteresis: bool
    ) -> NetworkQuality:
        """Apply detailed stability constraints (Cooldowns, Limits)."""
        # 1. Critical Cooldown
        if self._current_quality == NetworkQuality.CRITICAL:
            time_in_critical = time.time() - self._critical_entry_time
            if (
                time_in_critical < AdaptationConfig.CRITICAL_COOLDOWN
                and target_quality > NetworkQuality.CRITICAL
            ):
                # Force stay in CRITICAL
                return NetworkQuality.CRITICAL

        # 2. Level-by-Level Recovery Limit (only applies if recovering and NOT bypassing)
        if target_quality > self._current_quality and not bypass_hysteresis:
            current_val = self._current_quality.value
            target_val = target_quality.value
            if target_val > current_val + AdaptationConfig.RECOVERY_STEP_LIMIT:
                capped_val = current_val + AdaptationConfig.RECOVERY_STEP_LIMIT
                target_quality = NetworkQuality(capped_val)

        # 3. Special EXCELLENT Check (Sustained Stability)
        if target_quality == NetworkQuality.EXCELLENT and not bypass_hysteresis:
            if not (
                self._current_quality >= NetworkQuality.STABLE
                and self._stable_duration > 60
            ):
                return NetworkQuality.STABLE

        return target_quality

    def _apply_hysteresis(
        self,
        target_quality: NetworkQuality,
        bypass: bool,
        metrics: dict,
        reason: str = None,
    ):
        """Apply hysteresis logic and trigger transition if needed."""
        if bypass:
            # Immediate transition if target different
            if target_quality != self._current_quality:
                self._transition_to(
                    target_quality,
                    metrics["moderate_errors"],
                    metrics["total_events"],
                    reason,
                )
                self._reset_hysteresis()
            return

        if target_quality < self._current_quality:
            # Degrading
            self._consecutive_bad_windows += 1
            self._consecutive_good_windows = 0

            if self._consecutive_bad_windows >= AdaptationConfig.DEGRADATION_THRESHOLD:
                self._transition_to(
                    target_quality,
                    metrics["moderate_errors"],
                    metrics["total_events"],
                    reason,
                )
                self._consecutive_bad_windows = 0

        elif target_quality > self._current_quality:
            # Recovering
            self._consecutive_good_windows += 1
            self._consecutive_bad_windows = 0

            if self._consecutive_good_windows >= AdaptationConfig.RECOVERY_THRESHOLD:
                self._transition_to(
                    target_quality,
                    metrics["moderate_errors"],
                    metrics["total_events"],
                    reason,
                )
                self._consecutive_good_windows = 0
        else:
            # Stable state
            self._reset_hysteresis()

            # Track stable duration
            if self._current_quality == NetworkQuality.STABLE:
                self._stable_duration = time.time() - self._last_window_update

    def _reset_hysteresis(self):
        """Reset hysteresis counters."""
        self._consecutive_bad_windows = 0
        self._consecutive_good_windows = 0

    def _transition_to(
        self,
        new_quality: NetworkQuality,
        window_errors: int,
        window_total: int,
        reason: str = None,
    ):
        """
        Transition to a new quality state (must be called under lock).

        Args:
            new_quality: Target state
            window_errors: Error count in current window
            window_total: Total event count in current window
            reason: Optional description of trigger (e.g. fast-path)
        """
        if new_quality == self._current_quality:
            return

        old_quality = self._current_quality
        self._current_quality = new_quality
        self._last_window_update = time.time()
        self._stable_duration = 0.0

        # Track entry time for CRITICAL state
        if new_quality == NetworkQuality.CRITICAL:
            self._critical_entry_time = time.time()

        # Log state transition with WINDOW SPECIFIC metrics
        reason_str = f" ({reason})" if reason else ""
        logger.info(
            f"[NetworkObserver] Quality: {old_quality.name_str} → {new_quality.name_str} "
            f"(current_window_errors: {window_errors}/{window_total}){reason_str}"
        )

        # Notify callbacks
        for callback in self._state_callbacks:
            try:
                callback(new_quality)
            except Exception as e:
                logger.error(f"[NetworkObserver] Callback error: {e}")

    def reset(self):
        """Reset all metrics and state (thread-safe)."""
        with self._lock:
            self._metrics = NetworkMetrics()
            self._error_history.clear()
            self._handshake_history.clear()
            self._current_quality = NetworkQuality.STABLE
            self._consecutive_bad_windows = 0
            self._consecutive_good_windows = 0
            self._stable_duration = 0.0

            # Reset rolling counters
            self._rolling_counts = {"moderate_errors": 0, "reconnects": 0, "crashes": 0}

            logger.info("[NetworkObserver] Metrics reset")
