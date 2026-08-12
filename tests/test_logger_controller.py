"""Unit tests for LoggerController metric formatting."""

from __future__ import annotations

import pytest

from src.ui.controllers.logger_controller import LoggerController


def test_logger_controller_memory_formatting():
    """Test RAM formatting and ratio calculation."""
    metric = LoggerController.format_memory(512.0, 1024.0)
    assert metric.text == "512.0 / 1024 MB"
    assert metric.ratio == pytest.approx(0.5)


def test_logger_controller_threads_formatting():
    """Test active thread nodes formatting."""
    metric = LoggerController.format_threads(14)
    assert "14" in metric.text
    assert metric.status is not None


def test_logger_controller_health_formatting():
    """Test system health issues formatting."""
    metric = LoggerController.format_health(0)
    assert "0" in metric.text
    assert metric.message is not None
