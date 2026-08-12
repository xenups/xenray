"""Tests for ConnectionButton animation scheduling (page.run_task RuntimeError fix).

``set_connected`` / ``set_connecting`` / ``set_disconnecting`` start pulse/glow
animation loops. These methods are invoked both from background workers (via
``page.run_task``) and directly on the Flet UI event loop (connection-state
events are marshaled onto the loop). ``_schedule_animation_task`` must create the
task directly on the active loop (never raise RuntimeError) when already on the
Flet event loop, and fall back to ``page.run_task`` from any other thread.
"""

import asyncio

import pytest

# Imported first to pre-warm the UI package graph (avoids the pre-existing
# server_list <-> chain_builder_page circular import when a components module is
# the first UI import in the process). Same pattern as test_ui_views_and_services.py.
from src.ui.components.common.toast import ToastManager  # noqa: F401
from src.ui.components.dashboard.connection_button import _schedule_animation_task


class _FakePage:
    def __init__(self):
        self.run_task_calls = []

    def run_task(self, fn):
        self.run_task_calls.append(fn)
        return None


class _FakeSession:
    def __init__(self, loop):
        self.connection = type("C", (), {"loop": loop})()


def test_schedule_animation_off_loop_uses_run_task():
    """No running loop (background thread) -> schedule onto the page loop."""
    page = _FakePage()

    async def anim():
        pass

    _schedule_animation_task(page, anim)

    assert page.run_task_calls == [anim]


@pytest.mark.asyncio
async def test_schedule_animation_on_page_loop_uses_create_task():
    """Already on the Flet event loop -> create_task, never run_task (no RuntimeError)."""
    running = asyncio.get_running_loop()
    page = _FakePage()
    page.session = _FakeSession(running)

    async def anim():
        pass

    task = _schedule_animation_task(page, anim)

    # The animation task is created on the active loop — it actually runs.
    assert isinstance(task, asyncio.Task)
    assert page.run_task_calls == []
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_schedule_animation_on_foreign_loop_uses_run_task():
    """A running loop that is NOT the page loop -> still schedule onto the page loop."""
    other = asyncio.new_event_loop()  # different loop object, not running
    page = _FakePage()
    page.session = _FakeSession(other)

    async def anim():
        pass

    _schedule_animation_task(page, anim)

    assert page.run_task_calls == [anim]
    other.close()


@pytest.mark.asyncio
async def test_schedule_animation_task_actually_runs_on_loop():
    """The task scheduled via create_task executes its body on the event loop."""
    running = asyncio.get_running_loop()
    page = _FakePage()
    page.session = _FakeSession(running)

    ran = []

    async def anim():
        ran.append("tick")

    task = _schedule_animation_task(page, anim)
    await task

    assert ran == ["tick"]


def test_schedule_animation_none_page_returns_none():
    """A detached control (no page) must not schedule anything."""

    async def anim():
        pass

    assert _schedule_animation_task(None, anim) is None
