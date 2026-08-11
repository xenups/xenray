"""Tests for SplashScreen minimum-display enforcement and dismissal."""

from __future__ import annotations

import asyncio
import time

from src.ui.components.splash_screen import SplashScreen


def test_entrance_animation_resets_display_clock():
    splash = SplashScreen()

    # Simulate a slow UI build (> min display window) BEFORE the splash appears.
    time.sleep(1.5)
    splash.trigger_entrance_animation()

    # The min-display clock starts at entrance, not construction.
    assert time.time() - splash._start_time < 0.1


def test_dismiss_enforces_min_display_after_entrance():
    splash = SplashScreen()
    splash.trigger_entrance_animation()

    start = time.time()
    asyncio.run(splash.dismiss_when_ready(None))
    elapsed = time.time() - start

    # MIN_DISPLAY_SECONDS (1.2s) is honored from entrance animation.
    assert elapsed >= 1.1
    assert splash._dismissed is True
