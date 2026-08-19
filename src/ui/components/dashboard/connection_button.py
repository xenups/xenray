"""Connection button component with animated glow, sweep disc, and embedded status/timer."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.ui.components.dashboard.connection_glow_layer import ConnectionGlowLayer
from src.ui.controllers.connection_button_controller import ConnectionButtonController
from src.ui.helpers.connection_animation_helper import schedule_animation_task

# Re-export for backward compatibility
_schedule_animation_task = schedule_animation_task


class ConnectionButton(ft.Container):
    """Flet composite widget for the circular connection power button."""

    def __init__(self, on_click: Optional[Callable] = None):
        # 1. Main Power Icon (Proportional size = 42)
        self._icon = ft.Icon(ft.Icons.POWER_SETTINGS_NEW, size=42, color=ft.Colors.WHITE)

        # 2. Connection Status Text inside button (size=12, W_500)
        self._status_text = ft.Text(
            "Disconnected",
            size=12,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.WHITE_70,
            text_align=ft.TextAlign.CENTER,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        # 3. Connection Timer inside button (size=11, opacity=0.5, monospace)
        self._uptime_text = ft.Text(
            "00:00:00",
            size=11,
            color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE),
            font_family="monospace",
            text_align=ft.TextAlign.CENTER,
        )

        # 4. Controller handling state, animations, and transitions
        self._controller = ConnectionButtonController(self, on_click)

        # 5. Vertical Content Column centered inside circular power button
        self._content_column = ft.Column(
            controls=[
                self._icon,
                self._status_text,
                self._uptime_text,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=3,
        )

        # 6. Outer Ambient Glow Layer
        self._glow_layer = ConnectionGlowLayer()

        # 7. Rotating sweep disc (behind button)
        self._border_container = ft.Container(
            width=170,
            height=170,
            border_radius=85,
            gradient=None,
            visible=False,
            rotate=ft.Rotate(angle=0.0),
            animate_rotation=ft.Animation(
                duration=1500,
                curve=ft.AnimationCurve.LINEAR,
            ),
        )

        # 8. Static opaque mask behind button (165px)
        self._mask = ft.Container(
            width=165,
            height=165,
            border_radius=82.5,
            bgcolor="#0f172a",
            visible=False,
        )

        # 9. Inner clickable 165x165 glass button
        self._button = ft.Container(
            content=self._content_column,
            width=165,
            height=165,
            border_radius=82.5,
            bgcolor=ft.Colors.with_opacity(0.15, "#1e293b"),
            border=ft.Border.all(1.5, ft.Colors.with_opacity(0.2, ft.Colors.WHITE)),
            on_click=self._controller.on_button_click,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        )

        super().__init__(
            content=ft.Stack(
                [
                    self._glow_layer,
                    self._border_container,
                    self._mask,
                    self._button,
                ],
                alignment=ft.Alignment.CENTER,
            ),
            width=195,
            height=195,
            alignment=ft.Alignment.CENTER,
        )

    # -----------------------------------------------------------------------
    # State & Attribute Compatibility Properties
    # -----------------------------------------------------------------------
    @property
    def _is_connected(self) -> bool:
        return self._controller._is_connected

    @_is_connected.setter
    def _is_connected(self, value: bool) -> None:
        self._controller._is_connected = value

    @property
    def _is_connecting(self) -> bool:
        return self._controller._is_connecting

    @_is_connecting.setter
    def _is_connecting(self, value: bool) -> None:
        self._controller._is_connecting = value

    @property
    def _state(self) -> str:
        return self._controller._state

    @_state.setter
    def _state(self, value: str) -> None:
        self._controller._state = value

    @property
    def _current_activity(self) -> float:
        return self._controller._current_activity

    @_current_activity.setter
    def _current_activity(self, value: float) -> None:
        self._controller._current_activity = value

    @property
    def _state_generation(self) -> int:
        return self._controller._state_generation

    @_state_generation.setter
    def _state_generation(self, value: int) -> None:
        self._controller._state_generation = value

    @property
    def _anim_task(self):
        return self._controller._anim_task

    @_anim_task.setter
    def _anim_task(self, value) -> None:
        self._controller._anim_task = value

    @property
    def _ping_anim_task(self):
        return self._controller._ping_anim_task

    @_ping_anim_task.setter
    def _ping_anim_task(self, value) -> None:
        self._controller._ping_anim_task = value

    @property
    def _pending_ping_start(self) -> bool:
        return self._controller._pending_ping_start

    @_pending_ping_start.setter
    def _pending_ping_start(self, value: bool) -> None:
        self._controller._pending_ping_start = value

    @property
    def _ping_animating(self) -> bool:
        return self._controller._ping_animating

    @_ping_animating.setter
    def _ping_animating(self, value: bool) -> None:
        self._controller._ping_animating = value

    @property
    def _is_pinging(self) -> bool:
        return self._controller._is_pinging

    @_is_pinging.setter
    def _is_pinging(self, value: bool) -> None:
        self._controller._is_pinging = value

    # -----------------------------------------------------------------------
    # Public API Delegations
    # -----------------------------------------------------------------------
    def did_mount(self) -> None:
        """Flet lifecycle hook."""
        self._controller.did_mount()

    def update_theme(self, is_dark: bool) -> None:
        """Update button appearance based on theme."""
        self._controller.update_theme(is_dark)

    def set_connected(self, status_label: Optional[str] = None) -> None:
        """Set button to connected state."""
        self._controller.set_connected(status_label)

    def set_disconnected(self, status_label: Optional[str] = None) -> None:
        """Set button to disconnected state."""
        self._controller.set_disconnected(status_label)

    def set_connecting(self, status_label: Optional[str] = None) -> None:
        """Set connecting state with amber pulse."""
        self._controller.set_connecting(status_label)

    def set_disconnecting(self, status_label: str = "Disconnecting...") -> None:
        """Set disconnecting state with red pulse."""
        self._controller.set_disconnecting(status_label)

    def set_step(self, step_msg: str) -> None:
        """Update status text during connection step transitions."""
        self._controller.set_step(step_msg)

    def start_ping_animation(self) -> None:
        """Start native neon sweep around button."""
        self._controller.start_ping_animation()

    def stop_ping_animation(self) -> None:
        """Remove neon sweep and mask instantly."""
        self._controller.stop_ping_animation()

    def set_pre_connection_ping(self, latency_text: str | int | float, is_success: bool) -> None:
        """Show pre-connection latency result on status line."""
        self._controller.set_pre_connection_ping(latency_text, is_success)

    def update_uptime(self, elapsed: int | float | str) -> None:
        """Update uptime timer text inside button."""
        self._controller.update_uptime(elapsed)

    def set_uptime(self, uptime_str: str) -> None:
        """Update uptime timer text inside button."""
        self._controller.update_uptime(uptime_str)

    def set_online_status(self, is_online: bool) -> None:
        """Update online status indicator."""
        self._controller.set_online_status(is_online)

    def update_network_activity(self, total_bps: float) -> None:
        """Update glow layer using network activity."""
        self._controller.update_network_activity(total_bps)

    def _has_page_attached(self) -> bool:
        try:
            return self.page is not None
        except (RuntimeError, AttributeError):
            return False

    def _schedule_animation(self, coro_factory):
        try:
            page = self.page
        except Exception:
            page = None
        if page is None:
            return None
        return schedule_animation_task(page, coro_factory)
