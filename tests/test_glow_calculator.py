"""Unit tests for GlowCalculator traffic normalization and physics calculations."""

from __future__ import annotations

import pytest

from src.ui.helpers.glow_calculator import GlowCalculator, GlowMetrics


def test_glow_calculator_activity_ranges():
    """Test piecewise activity calculation across traffic thresholds."""
    assert GlowCalculator.calculate_activity(0) == 0
    assert GlowCalculator.calculate_activity(5 * 1024) == 5
    assert GlowCalculator.calculate_activity(100 * 1024) == 38
    assert GlowCalculator.calculate_activity(1000 * 1024) == 73
    assert GlowCalculator.calculate_activity(5000 * 1024) == 95


def test_glow_calculator_hysteresis():
    """Test that metrics return None when change is below hysteresis threshold."""
    metrics1 = GlowCalculator.compute_glow_metrics(100 * 1024, current_activity=0)
    assert metrics1 is not None
    assert isinstance(metrics1, GlowMetrics)

    # Small BPS change resulting in activity difference < 2 should return None
    metrics2 = GlowCalculator.compute_glow_metrics(102 * 1024, current_activity=metrics1.activity)
    assert metrics2 is None


def test_glow_calculator_clamping():
    """Test that blur, spread, opacity, and scale remain within visual clamping bounds."""
    metrics = GlowCalculator.compute_glow_metrics(10000 * 1024, current_activity=0)
    assert metrics is not None
    assert 18.0 <= metrics.blur <= 35.0
    assert 0.0 <= metrics.spread <= 4.0
    assert 0.2 <= metrics.opacity <= 0.35
    assert 1.0 <= metrics.scale <= 1.02
