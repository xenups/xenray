"""Unit tests for the ToastManager overlay pipeline."""

from __future__ import annotations

import flet as ft
import pytest

from src.ui.components.common.toast import ToastManager


class _FakeOverlay:
    def __init__(self):
        self.controls = []
        self.updated = 0

    def append(self, control):
        self.controls.append(control)

    def update(self):
        self.updated += 1


class _FakePage:
    def __init__(self):
        self.overlay = _FakeOverlay()
        self.tasks = []

    def update(self, *controls):
        for c in controls:
            if hasattr(c, "updated"):
                c.updated += 1

    def run_task(self, coro, *args, **kwargs):
        self.tasks.append((coro, args, kwargs))


def test_manager_mounts_persistent_toast_layer_on_overlay():
    """A persistent top-center layer must be mounted once on page.overlay."""
    page = _FakePage()
    manager = ToastManager(page)

    assert len(page.overlay.controls) == 1
    assert page.overlay.controls[0] is manager._toast_layer
    assert isinstance(manager._toast_layer, ft.Stack)


def test_show_appends_into_layer_not_overlay():
    """show() must push the toast into the isolated layer and update ONLY that
    layer — never re-diff the whole page.overlay (whose snapshot can desync)."""
    page = _FakePage()
    manager = ToastManager(page)
    layer = manager._toast_layer
    overlay_updates_after_mount = page.overlay.updated

    manager.show("Hello", "success", 2000)

    assert len(layer.controls) == 1
    assert layer.visible is True
    # Overlay still only holds the layer; show() did not touch it.
    assert len(page.overlay.controls) == 1
    assert page.overlay.updated == overlay_updates_after_mount
    # Auto-dismiss coroutine scheduled.
    assert len(page.tasks) == 1


def test_show_replaces_previous_toast():
    """Successive toasts replace the previous one in the layer."""
    page = _FakePage()
    manager = ToastManager(page)
    layer = manager._toast_layer

    manager.show("First", "info")
    assert len(layer.controls) == 1
    first = layer.controls[0]

    manager.show("Second", "error")
    assert len(layer.controls) == 1
    assert layer.controls[0] is not first
