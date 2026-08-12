"""Glow Calculator - Pure mathematical utility for traffic activity normalization and visual glow physics."""

from __future__ import annotations

from typing import NamedTuple, Optional


class GlowMetrics(NamedTuple):
    """Calculated physical glow parameters for connection button visual state."""

    activity: int
    blur: float
    spread: float
    opacity: float
    scale: float
    glow_opacity: float


class GlowCalculator:
    """Pure mathematical calculator for network traffic activity scores and glow physics."""

    @staticmethod
    def calculate_activity(total_bps: float) -> int:
        """Calculate piecewise normalized activity score (0-100) from raw throughput BPS."""
        kb_per_sec = max(0.0, float(total_bps) / 1024.0)

        if kb_per_sec < 10:
            activity = int(kb_per_sec * 1)
        elif kb_per_sec < 50:
            activity = int(10 + (kb_per_sec / 50) * 25)
        elif kb_per_sec < 500:
            activity = int(35 + ((kb_per_sec - 50) / 450) * 30)
        elif kb_per_sec < 2000:
            activity = int(65 + ((kb_per_sec - 500) / 1500) * 25)
        else:
            activity = min(100, int(90 + (kb_per_sec / 10000) * 10))

        return max(0, min(100, activity))

    @classmethod
    def compute_glow_metrics(
        cls,
        total_bps: float,
        current_activity: int = 0,
        hysteresis_threshold: int = 2,
    ) -> Optional[GlowMetrics]:
        """Compute glow physical parameters. Returns None if change is below hysteresis threshold."""
        activity = cls.calculate_activity(total_bps)

        if abs(activity - current_activity) < hysteresis_threshold and current_activity != 0:
            return None

        min_blur = 20.0
        max_blur = 35.0
        min_spread = 0.0
        max_spread = 4.0

        ratio = activity / 100.0
        blur = max(18.0, min(35.0, min_blur + (max_blur - min_blur) * ratio))
        spread = max(0.0, min(4.0, min_spread + (max_spread - min_spread) * ratio))
        opacity = max(0.2, min(0.35, 0.25 + 0.1 * ratio))
        scale = 1.0 + ratio * 0.02
        glow_opacity = 0.7 + ratio * 0.15

        return GlowMetrics(
            activity=activity,
            blur=blur,
            spread=spread,
            opacity=opacity,
            scale=scale,
            glow_opacity=glow_opacity,
        )
