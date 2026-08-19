"""Controller managing visual states, animations, and transitions for ConnectionButton."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

import flet as ft

from src.core.i18n import t
from src.core.logger import logger
from src.ui.helpers.button_animation_loops import (
    connected_breath_loop,
    connecting_pulse_loop,
    disconnecting_pulse_loop,
    ping_sweep_loop,
)
from src.ui.helpers.button_theme_styles import format_uptime, get_sweep_gradient
from src.ui.helpers.glow_calculator import GlowCalculator
from src.ui.helpers.status_helper import get_short_status_label

if TYPE_CHECKING:
    from src.ui.components.dashboard.connection_button import ConnectionButton


class ConnectionButtonController:
    """Orchestrates states, theme updates, FSM generation tokens, and animation loops."""

    def __init__(self, widget: ConnectionButton, user_on_click: Optional[Callable] = None):
        self._widget = widget
        self._user_on_click = user_on_click

        self._is_connected = False
        self._is_connecting = False
        self._current_activity = 0
        self._last_active = False
        self._state = "disconnected"

        self._state_generation = 0
        self._anim_task = None

        self._is_pinging = False
        self._ping_animating = False
        self._ping_anim_task = None
        self._pending_ping_start = False
        self._sweep_gradient = get_sweep_gradient()

    # -----------------------------------------------------------------------
    # Event Handlers
    # -----------------------------------------------------------------------
    def on_button_click(self, e) -> None:
        """Handle button click with FSM state and generation logging."""
        try:
            from src.core.fsm.connection_fsm import connection_fsm

            fsm_st = connection_fsm.state.value
        except Exception:
            fsm_st = "unknown"

        logger.info(f"[UI_BUTTON] Clicked in state={fsm_st} | Gen: {self._state_generation}")
        if self._user_on_click:
            self._user_on_click(e)

    # -----------------------------------------------------------------------
    # Lifecycle & Theme
    # -----------------------------------------------------------------------
    def did_mount(self) -> None:
        """Flet lifecycle hook — arm sweep disc baseline during mount."""
        self._widget._border_container.visible = True
        self._widget._border_container.rotate = ft.Rotate(angle=0.0)
        try:
            self._widget._border_container.update()
        except Exception:
            pass

        if self._pending_ping_start:
            self._pending_ping_start = False
            self._ping_animating = False
            self.start_ping_animation()

    def update_theme(self, is_dark: bool) -> None:
        """Update button appearance based on active theme."""
        if self._is_connected or self._is_connecting:
            return

        self._widget._button.opacity = 1.0
        self._widget._button.bgcolor = "#EDE9FE"
        self._widget._button.gradient = ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=["#F5F3FF", "#EDE9FE", "#DDD6FE"],
        )
        self._widget._button.border = ft.Border.all(2.0, ft.Colors.WHITE)
        self._widget._icon.color = "#1E1B4B"
        self._widget._status_text.color = "#1E1B4B"
        self._widget._uptime_text.color = "#8B8BA7"

        try:
            self._widget._button.update()
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Animation Scheduling & Cancellation
    # -----------------------------------------------------------------------
    def _has_page_attached(self) -> bool:
        """True when the control is attached to a page."""
        return self._widget._has_page_attached()

    def _cancel_anim_task(self) -> None:
        """Cancel any running UI animation loop."""
        if self._anim_task and hasattr(self._anim_task, "cancel"):
            try:
                self._anim_task.cancel()
            except Exception:
                pass
        self._anim_task = None

    def _schedule_animation(self, coro_factory):
        """Schedule an animation loop safely."""
        return self._widget._schedule_animation(coro_factory)

    # -----------------------------------------------------------------------
    # State Transitions
    # -----------------------------------------------------------------------
    def set_connected(self, status_label: Optional[str] = None) -> None:
        """Set button to connected state with solid rich lilac core and breath animation."""
        self._cancel_anim_task()
        self.stop_ping_animation()
        self._state_generation += 1
        current_gen = self._state_generation

        self._is_connected = True
        self._is_connecting = False
        self._state = "connected"

        label = get_short_status_label(status_label or t("app.connected"))

        # 100% Solid Opaque Lilac Core (never blends with background glow)
        self._widget._button.opacity = 1.0
        self._widget._button.bgcolor = "#EDE9FE"
        self._widget._button.gradient = ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=["#F5F3FF", "#EDE9FE", "#DDD6FE"],
        )
        self._widget._button.border = ft.Border.all(2.0, ft.Colors.WHITE)
        self._widget._icon.color = "#1E1B4B"
        self._widget._status_text.value = label
        self._widget._status_text.color = "#1E1B4B"
        self._widget._uptime_text.color = "#8B8BA7"
        try:
            self._widget._button.update()
        except Exception:
            pass

        self._widget._glow_layer.set_connected_glow()

        if self._has_page_attached():

            async def _connected_breath():
                await connected_breath_loop(
                    self._has_page_attached,
                    self._widget._glow_layer,
                    lambda: self._state == "connected" and self._state_generation == current_gen,
                    lambda: self._current_activity,
                )

            self._anim_task = self._schedule_animation(_connected_breath)

    def set_disconnected(self, status_label: Optional[str] = None) -> None:
        """Set button to disconnected state."""
        self._cancel_anim_task()
        self.stop_ping_animation()
        self._state_generation += 1
        self._is_connected = False
        self._is_connecting = False
        self._state = "disconnected"
        self._current_activity = 0

        label = get_short_status_label(status_label or t("app.disconnected"))

        # 100% Solid Opaque Lilac Core
        self._widget._button.opacity = 1.0
        self._widget._button.bgcolor = "#EDE9FE"
        self._widget._button.gradient = ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=["#F5F3FF", "#EDE9FE", "#DDD6FE"],
        )
        self._widget._button.border = ft.Border.all(2.0, ft.Colors.WHITE)
        self._widget._icon.color = "#1E1B4B"
        self._widget._status_text.value = label
        self._widget._status_text.color = "#1E1B4B"
        self._widget._uptime_text.value = "00:00:00"
        self._widget._uptime_text.color = "#8B8BA7"
        try:
            self._widget._button.update()
        except Exception:
            pass

        self._widget._glow_layer.set_disconnected_glow()

    def set_connecting(self, status_label: Optional[str] = None) -> None:
        """Set connecting state with solid core and indigo-violet glow pulse."""
        self._cancel_anim_task()
        self.stop_ping_animation()
        self._state_generation += 1
        current_gen = self._state_generation

        self._is_connected = False
        self._is_connecting = True
        self._state = "connecting"

        label = get_short_status_label(status_label or t("app.connecting"))

        self._widget._button.opacity = 1.0
        self._widget._button.bgcolor = "#EDE9FE"
        self._widget._button.gradient = ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=["#F5F3FF", "#EDE9FE", "#DDD6FE"],
        )
        self._widget._button.border = ft.Border.all(2.0, ft.Colors.WHITE)
        self._widget._icon.color = "#1E1B4B"
        self._widget._status_text.value = label
        self._widget._status_text.color = "#1E1B4B"
        self._widget._uptime_text.value = "00:00:00"
        self._widget._uptime_text.color = "#8B8BA7"
        try:
            self._widget._button.update()
        except Exception:
            pass

        self._widget._glow_layer.set_connecting_glow()

        if self._has_page_attached():

            async def _connecting_pulse():
                await connecting_pulse_loop(
                    self._has_page_attached,
                    self._widget._glow_layer,
                    lambda: self._is_connecting and self._state_generation == current_gen,
                )

            self._anim_task = self._schedule_animation(_connecting_pulse)

    def set_disconnecting(self, status_label: str = "Disconnecting...") -> None:
        """Set disconnecting state with solid core and pulse."""
        self._cancel_anim_task()
        self.stop_ping_animation()
        self._state_generation += 1
        current_gen = self._state_generation

        self._is_connected = False
        self._is_connecting = False
        self._state = "disconnecting"

        self._widget._button.opacity = 1.0
        self._widget._button.bgcolor = "#EDE9FE"
        self._widget._button.gradient = ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=["#F5F3FF", "#EDE9FE", "#DDD6FE"],
        )
        self._widget._button.border = ft.Border.all(2.0, ft.Colors.WHITE)
        self._widget._icon.color = "#1E1B4B"
        self._widget._status_text.value = status_label
        self._widget._status_text.color = "#1E1B4B"
        self._widget._uptime_text.color = "#8B8BA7"
        try:
            self._widget._button.update()
        except Exception:
            pass

        self._widget._glow_layer.set_disconnecting_glow()

        if self._has_page_attached():

            async def _disconnecting_pulse():
                await disconnecting_pulse_loop(
                    self._has_page_attached,
                    self._widget._glow_layer,
                    lambda: self._state == "disconnecting" and self._state_generation == current_gen,
                )

            self._anim_task = self._schedule_animation(_disconnecting_pulse)

    def set_step(self, step_msg: str) -> None:
        """Update center status text during connection step transitions."""
        if not step_msg or self._state != "connecting":
            return

        self._widget._status_text.value = get_short_status_label(step_msg)
        self._widget._status_text.color = "#1E1B4B"
        try:
            self._widget._status_text.update()
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Ping Animation & Status
    # -----------------------------------------------------------------------
    def start_ping_animation(self) -> None:
        """Start the native neon sweep around the button while ping runs."""
        if self._ping_animating:
            return
        self._ping_animating = True
        self._is_pinging = True

        if not self._has_page_attached():
            self._pending_ping_start = True
            return

        self._widget._border_container.visible = True
        self._widget._mask.visible = True
        self._widget._border_container.gradient = self._sweep_gradient
        try:
            self._widget._border_container.update()
        except Exception:
            pass
        try:
            self._widget._mask.update()
        except Exception:
            pass

        async def _ping_sweep():
            await ping_sweep_loop(
                self._widget._border_container,
                lambda: self._ping_animating,
            )

        self._ping_anim_task = self._schedule_animation(_ping_sweep)

    def stop_ping_animation(self) -> None:
        """Remove the neon sweep and mask instantly."""
        self._ping_animating = False
        self._is_pinging = False
        self._pending_ping_start = False
        if self._ping_anim_task and hasattr(self._ping_anim_task, "cancel"):
            try:
                self._ping_anim_task.cancel()
            except Exception:
                pass
        self._ping_anim_task = None
        self._widget._border_container.rotate = ft.Rotate(angle=0.0)
        self._widget._border_container.gradient = None
        self._widget._mask.visible = False
        try:
            self._widget._border_container.update()
        except Exception:
            pass
        try:
            self._widget._mask.update()
        except Exception:
            pass

    def set_pre_connection_ping(self, latency_text: str | int | float, is_success: bool) -> None:
        """Show a pre-connection latency result on the button's status line."""
        self.stop_ping_animation()
        if isinstance(latency_text, (int, float)):
            val_str = t("connection.latency_ms", value=int(latency_text)) if is_success else t("connection.error")
        else:
            val_str = str(latency_text) if latency_text else t("connection.error")
        self._widget._status_text.value = get_short_status_label(val_str)
        self._widget._status_text.color = ft.Colors.GREEN_400 if is_success else ft.Colors.RED_400
        try:
            self._widget._status_text.update()
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Activity & Metrics
    # -----------------------------------------------------------------------
    def update_uptime(self, elapsed: int | float | str) -> None:
        """Update uptime timer text inside the button."""
        self._widget._uptime_text.value = format_uptime(elapsed)
        try:
            if self._widget._uptime_text.page:
                self._widget._uptime_text.update()
        except Exception:
            pass

    def set_online_status(self, is_online: bool) -> None:
        """Update online status indicator (kept for API compatibility)."""
        if not is_online:
            self._widget._status_text.value = "Offline"
            self._widget._status_text.color = ft.Colors.RED_400
            try:
                self._widget._status_text.update()
            except Exception:
                pass

    def update_network_activity(self, total_bps: float) -> None:
        """Update glow layer visual properties using calculated GlowMetrics payload."""
        if self._state != "connected":
            return

        metrics = GlowCalculator.compute_glow_metrics(total_bps, self._current_activity)
        if metrics is None:
            return

        self._current_activity = metrics.activity
        self._widget._glow_layer.apply_activity_metrics(metrics)
