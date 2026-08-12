"""Tests for the Traffic Wave Visualizer smooth-animation behavior."""

from __future__ import annotations

import flet as ft

from src.ui.components.dashboard.wave_visualizer import WaveVisualizer


def test_wave_bars_use_smooth_ease_out_animation():
    wv = WaveVisualizer(num_bars=32)
    assert len(wv._dl_bars) == 32
    assert len(wv._ul_bars) == 32
    assert len(wv._bars) == 64

    for bar in wv._dl_bars + wv._ul_bars:
        assert bar.animate is not None
        assert bar.animate_size is not None
        assert bar.animate_size.duration in (400, 600)
        assert bar.animate_size.curve == ft.AnimationCurve.EASE_OUT


def test_bars_are_persistent_across_updates_no_recreation():
    wv = WaveVisualizer(num_bars=4)
    dl_before = list(wv._dl_bars)
    ul_before = list(wv._ul_bars)

    # Simulate the chart being attached (page reference set).
    wv._page = object()

    wv.update_heights([50.0] * 4, [80.0] * 4)
    wv.update_heights([20.0] * 4, [10.0] * 4)
    wv.reset_heights()

    # Exactly the same Container instances must be reused — nothing recreated.
    assert [id(b) for b in wv._dl_bars] == [id(b) for b in dl_before]
    assert [id(b) for b in wv._ul_bars] == [id(b) for b in ul_before]
    assert all(b.height == 6.0 for b in wv._dl_bars)
    assert all(b.height == 6.0 for b in wv._ul_bars)


def test_update_heights_noops_when_detached():
    wv = WaveVisualizer(num_bars=4)
    assert wv._is_attached() is False

    # Detached chart: heights must NOT be mutated (no wasted work while hidden).
    wv.update_heights([50.0] * 4, [80.0] * 4)
    assert all(b.height == 6.0 for b in wv._dl_bars)
    assert all(b.height == 6.0 for b in wv._ul_bars)
