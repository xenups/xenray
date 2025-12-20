"""Quality Evaluator - Determines network quality state from metrics."""

import time
from typing import Optional

from loguru import logger

from src.services.network_stability_observer import (AdaptationConfig,
                                                     ErrorSeverity, ErrorType,
                                                     NetworkQuality)


class QualityEvaluator:
    """Evaluates network quality based on error metrics and applies hysteresis logic."""

    def __init__(self):
        """Initialize QualityEvaluator."""
        self._current_quality = NetworkQuality.STABLE
        self._consecutive_good_windows = 0
        self._consecutive_bad_windows = 0
        self._stable_duration = 0.0
        self._critical_entry_time = 0.0
        self._last_transition_time = time.time()
        self._startup_time = time.time()

    def evaluate_quality(
        self,
        metrics: dict,
        error_history: list,
        last_success_time: float,
        last_error_time: float,
    ) -> tuple[NetworkQuality, Optional[str]]:
        """
        Evaluate network quality based on current metrics.

        Args:
            metrics: Window metrics dictionary
            error_history: List of recent error signals
            last_success_time: Timestamp of last success
            last_error_time: Timestamp of last error

        Returns:
            (quality_state, reason) tuple
        """
        now = time.time()

        # 1. Check Overrides (Fast Path / Silence)
        target_quality, bypass_hysteresis, reason = self._check_overrides(
            metrics, error_history, last_success_time, last_error_time, now
        )

        # 2. Standard Evaluation (if no override)
        if target_quality is None:
            target_quality = self._determine_base_quality(metrics)
            bypass_hysteresis = False

        # 3. Apply Stability Constraints (Cooldowns, Step Limits)
        target_quality = self._apply_stability_constraints(
            target_quality, bypass_hysteresis, now
        )

        # 4. Apply Hysteresis & Determine if Transition Needed
        should_transition, reason = self._should_transition(
            target_quality, bypass_hysteresis, metrics, reason
        )

        if should_transition:
            self._transition_to(target_quality, now)
            return target_quality, reason

        return self._current_quality, None

    def _check_overrides(
        self,
        metrics: dict,
        error_history: list,
        last_success_time: float,
        last_error_time: float,
        now: float,
    ) -> tuple[Optional[NetworkQuality], bool, Optional[str]]:
        """
        Check for conditions that override standard logic (Fast-Path, Silence).

        Returns:
            (TargetQuality, BypassHysteresis, Reason)
        """
        # A. Fast-Path Detection (Burst Logic - High Confidence Signals Only)
        high_confidence_types = {
            ErrorType.DNS_FAILURE,
            ErrorType.TIMEOUT,
            ErrorType.TLS_FAILURE,
            ErrorType.PROCESS_CRASH,
        }

        recent_burst_errors = sum(
            1
            for e in error_history
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
        elif (now - last_success_time) > AdaptationConfig.SILENCE_TIMEOUT and (
            now - last_error_time
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
        self, target_quality: NetworkQuality, bypass_hysteresis: bool, now: float
    ) -> NetworkQuality:
        """Apply detailed stability constraints (Cooldowns, Limits)."""
        # 1. Critical Cooldown
        if self._current_quality == NetworkQuality.CRITICAL:
            time_in_critical = now - self._critical_entry_time
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

    def _should_transition(
        self,
        target_quality: NetworkQuality,
        bypass: bool,
        metrics: dict,
        reason: str = None,
    ) -> tuple[bool, Optional[str]]:
        """Determine if quality state should transition based on hysteresis logic."""
        if bypass:
            # Immediate transition if target different
            if target_quality != self._current_quality:
                self._reset_hysteresis()
                return True, reason
            return False, None

        if target_quality < self._current_quality:
            # Degrading
            self._consecutive_bad_windows += 1
            self._consecutive_good_windows = 0

            if self._consecutive_bad_windows >= AdaptationConfig.DEGRADATION_THRESHOLD:
                self._consecutive_bad_windows = 0
                return True, f"degradation: {metrics['moderate_errors']} errors"

        elif target_quality > self._current_quality:
            # Recovering
            self._consecutive_good_windows += 1
            self._consecutive_bad_windows = 0

            if self._consecutive_good_windows >= AdaptationConfig.RECOVERY_THRESHOLD:
                self._consecutive_good_windows = 0
                return True, f"recovery: {metrics['moderate_errors']} errors"

        else:
            # Stable at current level
            self._consecutive_good_windows = 0
            self._consecutive_bad_windows = 0

        return False, None

    def _transition_to(self, new_quality: NetworkQuality, now: float):
        """Transition to new quality state."""
        old_quality = self._current_quality
        self._current_quality = new_quality
        self._last_transition_time = now

        # Track critical entry time
        if new_quality == NetworkQuality.CRITICAL:
            self._critical_entry_time = now

        # Track stable duration
        if new_quality >= NetworkQuality.STABLE:
            if old_quality >= NetworkQuality.STABLE:
                self._stable_duration += now - self._last_transition_time
            else:
                self._stable_duration = 0.0
        else:
            self._stable_duration = 0.0

        logger.info(
            f"[QualityEvaluator] Quality transition: {old_quality.name_str()} → {new_quality.name_str()}"
        )

    def _reset_hysteresis(self):
        """Reset hysteresis counters."""
        self._consecutive_good_windows = 0
        self._consecutive_bad_windows = 0

    @property
    def current_quality(self) -> NetworkQuality:
        """Get current quality state."""
        return self._current_quality
