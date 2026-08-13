"""Tests for the ConnectionButton first-ping-after-splash animation race."""

from __future__ import annotations

import types

from src.ui.components.dashboard.connection_button import ConnectionButton


class _FakePage:
    """Minimal page stub for did_mount tests."""

    def __init__(self):
        self.tasks = []

    def run_task(self, coro):
        self.tasks.append(coro)
        return None


def _build_button(page=None, pending_start: bool = False) -> ConnectionButton:
    btn = ConnectionButton(on_click=lambda e: None)
    if pending_start:
        # Simulate: start_ping_animation was called BEFORE the button mounted
        # (first ping right after splash) -> deferred.
        btn._pending_ping_start = True
        btn._ping_animating = True
        btn._is_pinging = True
    if page is not None:
        # Mount: Flet calls did_mount once the control is attached.
        btn._has_page_attached = lambda: True  # stub: attached now
        btn._schedule_animation = lambda coro_factory: page.tasks.append(coro_factory) or None
        btn.did_mount()
    else:
        btn._has_page_attached = lambda: False
    return btn


def test_start_before_mount_defers():
    """start_ping_animation without a page must defer, not silently drop."""
    btn = _build_button(page=None, pending_start=False)
    # Simulate call before mount: no page -> _pending_ping_start set
    btn._safe_page = lambda: None
    btn.start_ping_animation()
    assert btn._pending_ping_start is True
    assert btn._ping_animating is True


def test_did_mount_kicks_deferred_sweep():
    """did_mount must run the full start path for a deferred first ping."""
    page = _FakePage()
    btn = _build_button(page=page, pending_start=True)

    # did_mount consumed the flag and re-ran start_ping_animation -> the sweep
    # should be running (gradient set) and a task scheduled on the page.
    assert btn._pending_ping_start is False
    assert btn._ping_animating is True
    assert btn._border_container.gradient is not None
    assert page.tasks, "a sweep task should have been scheduled on the page"


def test_did_mount_without_pending_is_noop():
    page = _FakePage()
    btn = _build_button(page=page, pending_start=False)
    assert btn._pending_ping_start is False
    assert btn._ping_animating is False
    assert btn._border_container.gradient is None
    assert page.tasks == []


def test_stop_ping_clears_pending():
    btn = _build_button(page=None, pending_start=True)
    btn._safe_page = lambda: None
    btn.stop_ping_animation()
    assert btn._pending_ping_start is False
    assert btn._ping_animating is False
