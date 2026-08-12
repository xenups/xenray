"""Unit tests for SystemInfoCache, StartupWarmupManager, and SplashScreen startup pre-warming pipeline."""

from __future__ import annotations

import asyncio
import time

import flet as ft
import pytest

from src.core.startup_warmup_manager import StartupWarmupManager
from src.core.system_info_cache import system_info_cache
from src.ui.components.splash_screen import SplashScreen


def test_system_info_cache_warmup_and_snapshot():
    """Test system_info_cache populates OS metrics, hardware info, and system headers."""
    system_info_cache.clear()
    snapshot_before = system_info_cache.get_snapshot()
    assert snapshot_before.is_warmed_up is False

    snapshot = system_info_cache.warmup_system_info()
    assert snapshot.is_warmed_up is True
    assert len(snapshot.os_name) > 0
    assert snapshot.total_memory_mb > 0
    assert snapshot.cpu_cores_logical >= 1
    assert "OS" in snapshot.system_headers
    assert "RAM" in snapshot.system_headers


@pytest.mark.asyncio
async def test_startup_warmup_manager_pipeline_execution():
    """Test StartupWarmupManager runs pipeline tasks concurrently and sets is_warmed_up flag."""
    progress_statuses = []

    def progress_cb(status: str):
        progress_statuses.append(status)

    manager = StartupWarmupManager()
    assert manager.is_warmed_up is False

    result = await manager.execute_startup_pipeline(progress_callback=progress_cb)
    assert result is True
    assert manager.is_warmed_up is True
    assert len(progress_statuses) > 0


def test_splash_screen_controls_and_status_update():
    """Test SplashScreen UI structure and status label updates."""
    dismissed = []
    splash = SplashScreen(on_dismiss=lambda: dismissed.append(True))

    assert isinstance(splash, ft.Container)
    assert splash.bgcolor == "#0F111A"
    assert splash.opacity == 1.0
    assert splash.visible is True

    assert isinstance(splash._logo_image, ft.Image)
    assert splash._logo_image.src in ("assets/logo.png", "logo.png", "icon.png", "assets/icon.png", "assets/logo.svg")
    assert splash._title_text.value == "XenRay"
    assert isinstance(splash._loading_ring, ft.ProgressRing)

    splash.update_status("Pre-rendering views...")
    assert splash._status_text.value == "Pre-rendering views..."


@pytest.mark.asyncio
async def test_splash_screen_min_display_duration_constraint():
    """Test SplashScreen enforces MIN_DISPLAY_SECONDS display constraint before dismissing."""
    dismissed = []
    splash = SplashScreen(on_dismiss=lambda: dismissed.append(True))
    splash.MIN_DISPLAY_SECONDS = 0.3  # Shorter min time for fast test run

    start_time = time.time()
    await splash.dismiss_when_ready()
    elapsed = time.time() - start_time

    assert elapsed >= 0.3
    assert splash._dismissed is True
    assert splash.opacity == 0.0
    assert splash.visible is False
    assert dismissed == [True]


def test_warmup_dispatches_active_ping_and_publishes_result():
    """Active server ping runs at high priority during splash and pre-populates the dashboard."""
    from unittest.mock import MagicMock

    handler = MagicMock()
    handler.run_active_ping_sync.return_value = (True, "138ms", None)

    mw = MagicMock()
    mw._latency_monitor_handler = handler
    mw._selected_profile = {"id": "p1", "name": "S1", "config": {"outbounds": [{"protocol": "vless"}]}}

    manager = StartupWarmupManager(main_window=mw)
    asyncio.run(manager._warmup_active_server_ping())

    handler.run_active_ping_sync.assert_called_once()
    handler._on_ping_result.assert_called_once()
    call_args = handler._on_ping_result.call_args[0]
    assert call_args[1] is True
    assert call_args[2] == "138ms"


def test_warmup_skips_ping_when_no_active_profile():
    from unittest.mock import MagicMock

    handler = MagicMock()
    mw = MagicMock()
    mw._latency_monitor_handler = handler
    mw._selected_profile = None

    manager = StartupWarmupManager(main_window=mw)
    asyncio.run(manager._warmup_active_server_ping())

    handler.run_active_ping_sync.assert_not_called()
