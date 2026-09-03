"""SplashScreen Component - elegant animated initial startup overlay using project SVG logo asset."""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

import flet as ft

from src.core.i18n import t
from src.core.logger import logger
from src.ui.theme import AppColors


class SplashScreen(ft.Container):
    """Modern centered animated Splash Screen using SVG logo, brand text, and sleek loading ring."""

    MIN_DISPLAY_SECONDS: float = 1.2

    def __init__(self, on_dismiss: Optional[Callable[[], None]] = None) -> None:
        self._on_dismiss = on_dismiss
        self._start_time: float = time.time()
        self._dismissed: bool = False

        BG_COLOR = "#0F111A"
        WHITE = ft.Colors.WHITE

        # 1. Logo image with entrance scale/opacity transition
        self._logo_image = ft.Image(
            src="assets/logo.png",
            width=96,
            height=96,
            fit="contain",
        )

        self._logo_container = ft.Container(
            content=self._logo_image,
            width=96,
            height=96,
            alignment=ft.Alignment.CENTER,
            scale=ft.Scale(0.85),
            opacity=0.0,
            animate_scale=ft.Animation(600, ft.AnimationCurve.EASE_OUT),
            animate_opacity=ft.Animation(600, ft.AnimationCurve.EASE_OUT),
        )

        # 2. App Name Typography
        self._title_text = ft.Text(
            "XenRay",
            size=28,
            weight=ft.FontWeight.BOLD,
            color=WHITE,
        )

        # 3. Loading Ring Indicator with comfortable top margin
        self._loading_ring = ft.ProgressRing(
            width=22,
            height=22,
            stroke_width=2.5,
            color=AppColors.PRIMARY,
        )

        self._ring_container = ft.Container(
            content=self._loading_ring,
            margin=ft.Margin.only(top=24),
            alignment=ft.Alignment.CENTER,
        )

        # 4. Status Text
        self._status_text = ft.Text(
            t("splash.warming_up", default="Initializing Engine..."),
            size=11,
            color=ft.Colors.with_opacity(0.65, WHITE),
        )

        self._status_container = ft.Container(
            content=self._status_text,
            margin=ft.Margin.only(top=8),
            alignment=ft.Alignment.CENTER,
        )

        # Centered Vertical Column Stack
        content_column = ft.Column(
            controls=[
                self._logo_container,
                ft.Container(height=12),
                self._title_text,
                self._ring_container,
                self._status_container,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

        super().__init__(
            content=content_column,
            alignment=ft.Alignment.CENTER,
            bgcolor=BG_COLOR,
            expand=True,
            opacity=1.0,
            animate_opacity=ft.Animation(400, ft.AnimationCurve.EASE_IN_OUT),
        )

    def trigger_entrance_animation(self) -> None:
        """Trigger entrance scale and opacity animation when attached to page."""
        self._start_time = time.time()
        self._logo_container.scale = ft.Scale(1.0)
        self._logo_container.opacity = 1.0
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    def update_status(self, text: str) -> None:
        """Update startup progress status label."""
        self._status_text.value = text
        try:
            if self.page:
                self._status_text.update()
        except Exception:
            pass

    async def dismiss_when_ready(self, warmup_task: Optional[object] = None) -> None:
        """Wait for both warmup execution AND minimum splash display duration before fading out."""
        if self._dismissed:
            return

        if warmup_task:
            try:
                if asyncio.iscoroutine(warmup_task) or isinstance(warmup_task, asyncio.Future):
                    await warmup_task
                elif hasattr(warmup_task, "result"):
                    # Handle concurrent.futures.Future or Flet PageTask
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, warmup_task.result)
                elif callable(warmup_task):
                    res = warmup_task()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception as e:
                logger.error(f"[SplashScreen] Warmup task execution warning: {e}")

        # Enforce minimum display duration (~1.2s from entrance)
        elapsed = time.time() - self._start_time
        remaining = self.MIN_DISPLAY_SECONDS - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)

        # Smooth fade-out opacity animation
        self.opacity = 0.0
        try:
            if self.page:
                self.update()
        except Exception:
            pass

        await asyncio.sleep(0.4)  # Wait for 400ms opacity animation to complete
        self.visible = False
        self._dismissed = True

        if self._on_dismiss:
            try:
                self._on_dismiss()
            except Exception as e:
                logger.error(f"[SplashScreen] Error in on_dismiss callback: {e}")
