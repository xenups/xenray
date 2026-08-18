"""Tests for StatsForwardingService initialization timing (splash pre-warm).

User requirements (2026-08):
- «آمار موقع اسپلش اسکرین باید اینشیالایز بشه نه وقتی که رو صفحه اش کلیک میکنیم» —
  Statistics telemetry must initialize DURING the splash screen, not only when
  the user navigates to the Statistics page.
- «اطلاعات سیستم تو صفحه لاگ هم همینطور نباید چیزی برای نمایش دیلی دداشته باشه» —
  system info (memory/threads/health) on the Logs page must also be pre-warmed
  during splash — no delayed display when the page is opened.

Contract under test:
(a) forward_system_stats polls ALWAYS — the old `_active_tab != "logs"` gate is
    gone, so memory/threads/health updates land even while the active tab is
    "dashboard" (i.e. during splash).
(b) Both loops are update-then-sleep: the first poll happens immediately when
    the task starts, before the first 3s sleep.
(c) The `_nav_locked` guard is kept: while navigation is locked the system
    stats push is skipped.
(d) forward_network_stats is not tab-gated and also does an immediate first poll.
"""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import Mock, patch

# Imported first to pre-warm the UI package graph (avoids the pre-existing
# server_list <-> chain_builder_page circular import when a pages module is the
# first UI import in the process). Same pattern as test_core_crash_ui_reset.py.
from src.ui.components.common.toast import ToastManager  # noqa: F401
from src.ui.services.stats_forwarding_service import StatsForwardingService


class _StopLoop(Exception):
    """Raised from the mocked asyncio.sleep to stop the loop after one tick."""


def _make_mw(active_tab: str = "dashboard", nav_locked: bool = False, is_running: bool = True):
    """Build a minimal MainWindow stand-in exposing the attributes the service touches."""
    logs_view = Mock()
    mw = Mock()
    mw._active_tab = active_tab
    mw._nav_locked = nav_locked
    mw._is_running = is_running
    mw._stitch_logs_view = logs_view
    mw._network_stats = Mock()
    mw._network_stats.get_stats.return_value = {
        "download_speed": "1.2 MB/s",
        "total_bps": 1_000_000.0,
    }
    return mw, logs_view


@contextlib.contextmanager
def _run_one_tick(loop_method):
    """Run exactly one tick of a forwarding loop with asyncio.sleep short-circuited.

    The mocked ``asyncio.sleep`` records the requested delay then raises
    ``_StopLoop``, so the loop stops right after the first update+post-update
    sleep. The context manager exposes the recorded sleeps via ``.sleeps``.
    """
    recorded = {"sleeps": []}

    async def _sleep(seconds):
        recorded["sleeps"].append(seconds)
        raise _StopLoop

    with patch("src.ui.services.stats_forwarding_service.asyncio.sleep", side_effect=_sleep):
        try:
            asyncio.run(loop_method())
        except _StopLoop:
            pass
    yield recorded


# ---------------------------------------------------------------- system stats


def test_system_stats_polled_even_when_active_tab_is_not_logs():
    """The `_active_tab != 'logs'` gate is removed: updates land during splash."""
    mw, logs_view = _make_mw(active_tab="dashboard", nav_locked=False)
    with _run_one_tick(StatsForwardingService(mw).forward_system_stats):
        pass
    logs_view.update_memory.assert_called_once()
    logs_view.update_threads.assert_called_once()
    logs_view.update_health.assert_called_once()


def test_system_stats_first_poll_happens_before_first_sleep():
    """Immediate first poll: the update fires before asyncio.sleep is ever awaited."""
    mw, logs_view = _make_mw(active_tab="dashboard", nav_locked=False)
    with _run_one_tick(StatsForwardingService(mw).forward_system_stats) as tick:
        assert tick["sleeps"] == [3.0]
    logs_view.update_memory.assert_called_once()


def test_system_stats_skipped_while_nav_locked():
    """The _nav_locked guard is kept: locked navigation skips the push."""
    mw, logs_view = _make_mw(active_tab="dashboard", nav_locked=True)
    with _run_one_tick(StatsForwardingService(mw).forward_system_stats):
        pass
    logs_view.update_memory.assert_not_called()
    logs_view.update_threads.assert_not_called()
    logs_view.update_health.assert_not_called()


def test_system_stats_values_reach_logs_view():
    """The real psutil values flow through to the LogsView update methods."""
    mw, logs_view = _make_mw(active_tab="dashboard", nav_locked=False)
    with patch("src.ui.services.stats_forwarding_service.psutil.Process") as proc_cls, patch(
        "src.ui.services.stats_forwarding_service.psutil.virtual_memory"
    ) as vmem, patch("src.ui.services.stats_forwarding_service.threading.active_count", return_value=12):
        proc_cls.return_value.memory_info.return_value.rss = 256 * 1024 * 1024
        vmem.return_value.total = 16 * 1024 * 1024 * 1024
        with _run_one_tick(StatsForwardingService(mw).forward_system_stats):
            pass
    logs_view.update_memory.assert_called_once_with(256.0, 16384.0)
    logs_view.update_threads.assert_called_once_with(12)
    logs_view.update_health.assert_called_once_with(0)


# --------------------------------------------------------------- network stats


def test_network_stats_not_tab_gated_and_immediate_first_poll():
    """forward_network_stats has no active-tab gate and updates before sleeping."""
    mw, _ = _make_mw(active_tab="dashboard", nav_locked=False, is_running=True)
    with _run_one_tick(StatsForwardingService(mw).forward_network_stats) as tick:
        assert tick["sleeps"] == [3.0]  # the first sleep is only reached AFTER the first push
    assert mw._network_stats.get_stats.called  # the poll ran before the sleep


def test_network_stats_publishes_telemetry_on_first_tick():
    """The immediate first poll publishes a telemetry payload over the EventBus."""
    from src.core.event_bus import TOPIC_TELEMETRY_UPDATED, event_bus

    mw, _ = _make_mw(active_tab="dashboard", nav_locked=False, is_running=True)
    received = []
    event_bus.subscribe(TOPIC_TELEMETRY_UPDATED, lambda data: received.append(data))
    try:
        with _run_one_tick(StatsForwardingService(mw).forward_network_stats):
            pass
    finally:
        event_bus.clear()
    assert received, "first tick must publish telemetry immediately"
    assert received[0]["is_connected"] is True
