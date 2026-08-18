"""Tests for the reusable NeonSweepBorder component.

The sweep-glow animation is a SINGLE shared component (ConfigCard server
inspection, UpdateCard / XrayCoreCard update checks). These tests lock the
component contract: negative disc offsets (never a layout child), opaque
inner mask, start()/stop() gradient toggling and the is_animating state.
"""

from __future__ import annotations

import asyncio
import math

import flet as ft
import pytest

from src.ui.components.common.neon_sweep_border import SWEEP_COLORS, SWEEP_STOPS, NeonSweepBorder


def _make_border(width=150, height=32):
    return NeonSweepBorder(child=ft.Text("x"), width=width, height=height, border_radius=8)


def test_constructs_with_text_child():
    """The component wraps any control (e.g. ft.Text) in the border frame."""
    border = _make_border()
    assert isinstance(border, ft.Container)
    assert border.content is not None
    assert border._inner.content is not None


def test_disc_positioned_negative_offsets():
    """The 400px disc uses NEGATIVE left/top so it never sizes the Stack."""
    border = _make_border(width=150, height=32)
    assert border._disc.left < 0
    assert border._disc.top < 0
    assert border._disc.width == border._disc.height


def test_opaque_inner_mask_present():
    """The opaque inner layer masks the disc center (only the rim shows)."""
    border = _make_border()
    assert border._inner.bgcolor == "#161922"
    assert border._inner.clip_behavior == ft.ClipBehavior.HARD_EDGE


def test_gradient_palette_matches_config_card():
    """The sweep colors/stops are the original ConfigCard inspection values."""
    assert SWEEP_COLORS == ["#A3A8FE", "#00F2FE", "#00000000", "#00000000"]
    assert SWEEP_STOPS == [0.0, 0.10, 0.22, 1.0]


def test_start_arms_gradient_and_animating_state():
    """start(): gradient set + is_animating True (idle -> armed)."""
    border = _make_border()
    assert border._disc.gradient is None
    assert border.is_animating is False

    border.start()

    assert border.is_animating is True
    assert border._disc.gradient is border._sweep_gradient
    border.stop()


def test_start_is_idempotent():
    """Repeated start() while animating is a no-op."""
    border = _make_border()
    border.start()
    border.start()
    assert border.is_animating is True
    border.stop()


def test_stop_clears_gradient_and_animating_state():
    """stop(): gradient back to None + is_animating False + rotation reset."""
    border = _make_border()
    border.start()
    border.stop()

    assert border.is_animating is False
    assert border._disc.gradient is None
    assert border._disc.rotate.angle == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_animation_loop_rotates_disc():
    """The sweep loop rotates the disc a full turn after the frame flush."""
    border = _make_border()
    border.start()
    border.did_mount()  # mount race: still animating -> schedule the loop
    await asyncio.sleep(0.1)
    assert border._disc.rotate.angle == pytest.approx(2 * math.pi)
    border.stop()


def test_resize_disc_sizes_to_diagonal():
    """resize_disc() sizes the disc to the wrapper's diagonal."""
    border = _make_border()
    border.resize_disc(280.0, 65.0)
    expected = math.hypot(280.0, 65.0)
    assert border._disc.width == pytest.approx(expected)
    assert border._disc.height == pytest.approx(expected)
    assert border._disc.left == pytest.approx((280.0 - expected) / 2)
    assert border._disc.top == pytest.approx((65.0 - expected) / 2)


class _FakePage:
    """Minimal page stub exposing the run_task contract."""

    def __init__(self, loop):
        self._loop = loop

    def run_task(self, handler, *args, **kwargs):
        return asyncio.run_coroutine_threadsafe(handler(*args, **kwargs), self._loop)


@pytest.mark.asyncio
async def test_start_schedules_via_page_loop(monkeypatch):
    """A mounted border schedules the sweep loop through the page loop."""
    border = _make_border()
    page = _FakePage(asyncio.get_running_loop())
    monkeypatch.setattr(border, "_safe_page", lambda: page)

    border.start()
    border.did_mount()
    await asyncio.sleep(0.1)

    assert border.is_animating is True
    assert border._disc.rotate.angle != 0.0
    border.stop()
