"""Connection button component with animated glow, rotating neon sweep ring,
and embedded status/timer."""

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
        # 1. Main Power Icon — dark indigo on the bold lilac core.
        self._icon = ft.Icon(ft.Icons.POWER_SETTINGS_NEW, size=44, color="#1E1B4B")

        # 2. Connection Status Text inside button
        self._status_text = ft.Text(
            "Disconnected",
            size=13,
            weight=ft.FontWeight.W_500,
            color="#1E1B4B",
            text_align=ft.TextAlign.CENTER,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        # 3. Connection Timer inside button (subtle muted monospace timer)
        self._uptime_text = ft.Text(
            "00:00:00",
            size=10,
            color="#8B8BA7",
            font_family="monospace",
            weight=ft.FontWeight.W_400,
            text_align=ft.TextAlign.CENTER,
            visible=True,
        )

        # 4. Controller handling state, animations, and transitions
        self._controller = ConnectionButtonController(self, on_click)

        # 5. Vertical content column inside the circular button
        self._content_column = ft.Column(
            controls=[self._icon, self._status_text, self._uptime_text],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        )

        # 6. Outer ambient glow layer (soft blurred halo behind the disc)
        self._glow_layer = ConnectionGlowLayer()

        # 7. Rotating neon sweep ring (the disc the controller spins).
        self._border_container = ft.Container(
            width=178,
            height=178,
            border_radius=89,
            gradient=None,
            visible=False,
            rotate=ft.Rotate(angle=0.0),
            animate_rotation=ft.Animation(
                duration=1500,
                curve=ft.AnimationCurve.LINEAR,
            ),
        )

        # 8. Static opaque mask behind button so the sweep only shows as a rim.
        self._mask = ft.Container(
            width=165,
            height=165,
            border_radius=82.5,
            bgcolor="#0B0813",
            visible=False,
        )

        # 9. Inner clickable 165x165 button — 100% solid opaque lilac core (never blends with underlying glow)
        self._button = ft.Container(
            content=self._content_column,
            width=165,
            height=165,
            border_radius=82.5,
            opacity=1.0,
            bgcolor="#EDE9FE",
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[
                    "#F5F3FF",
                    "#EDE9FE",
                    "#DDD6FE",
                ],
            ),
            border=ft.Border.all(2.0, ft.Colors.WHITE),
            on_click=self._controller.on_button_click,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=16,
                color=ft.Colors.with_opacity(0.35, "#A78BFA"),
                offset=ft.Offset(0, 3),
            ),
        )

        super().__init__(
            content=ft.Stack(
                [
                    self._glow_layer,
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
        self._controller.did_mount()

    def update_theme(self, is_dark: bool) -> None:
        self._controller.update_theme(is_dark)

    def set_connected(self, status_label: Optional[str] = None) -> None:
        self._controller.set_connected(status_label)

    def set_disconnected(self, status_label: Optional[str] = None) -> None:
        self._controller.set_disconnected(status_label)

    def set_connecting(self, status_label: Optional[str] = None) -> None:
        self._controller.set_connecting(status_label)

    def set_disconnecting(self, status_label: str = "Disconnecting...") -> None:
        self._controller.set_disconnecting(status_label)

    def set_step(self, step_msg: str) -> None:
        self._controller.set_step(step_msg)

    def start_ping_animation(self) -> None:
        self._controller.start_ping_animation()

    def stop_ping_animation(self) -> None:
        self._controller.stop_ping_animation()

    def set_pre_connection_ping(self, latency_text, is_success: bool) -> None:
        self._controller.set_pre_connection_ping(latency_text, is_success)

    def update_uptime(self, elapsed) -> None:
        self._controller.update_uptime(elapsed)

    def set_uptime(self, uptime_str: str) -> None:
        self._controller.update_uptime(uptime_str)

    def set_online_status(self, is_online: bool) -> None:
        self._controller.set_online_status(is_online)

    def update_network_activity(self, total_bps: float) -> None:
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
