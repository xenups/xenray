"""Unit tests for NavSidebar LAN sharing fade-green indicator light.

Covers the status-light dot (``_lan_indicator``) that fades between dim
(0.15) and lit (1.0) with a 700ms EASE_OUT animation whenever LAN sharing
is enabled/disabled, plus the ``update_lan_badge`` delegation used by
``LanSharingPage``.
"""

from __future__ import annotations

import flet as ft

from src.ui.components.common.nav_sidebar import NavSidebar


def _make_sidebar(allow_lan: bool) -> NavSidebar:
    """Build a NavSidebar with the minimal required callbacks."""
    return NavSidebar(
        active_tab="dashboard",
        on_tab_change=lambda t: None,
        on_connect_click=lambda: None,
        allow_lan=allow_lan,
    )


def test_constructor_allow_lan_true_indicator_lit():
    """LAN enabled at construction → indicator starts lit (opacity 1.0)."""
    sb = _make_sidebar(allow_lan=True)
    assert sb._lan_indicator.opacity == 1.0


def test_constructor_allow_lan_false_indicator_dim():
    """LAN disabled at construction → indicator starts dim (opacity 0.15)."""
    sb = _make_sidebar(allow_lan=False)
    assert sb._lan_indicator.opacity == 0.15


def test_update_lan_button_flips_indicator_opacity():
    """update_lan_button(True/False) fades the indicator between lit and dim."""
    sb = _make_sidebar(allow_lan=False)
    assert sb._lan_indicator.opacity == 0.15

    sb.update_lan_button(True)
    assert sb._lan_indicator.opacity == 1.0

    sb.update_lan_button(False)
    assert sb._lan_indicator.opacity == 0.15


def test_update_lan_badge_delegates_to_update_lan_button():
    """update_lan_badge flips the indicator exactly like update_lan_button."""
    sb = _make_sidebar(allow_lan=False)
    assert sb._lan_indicator.opacity == 0.15

    sb.update_lan_badge(True)
    assert sb._lan_indicator.opacity == 1.0

    sb.update_lan_badge(False)
    assert sb._lan_indicator.opacity == 0.15


def test_indicator_uses_700ms_ease_out_fade_animation():
    """The indicator fades via a 700ms EASE_OUT animate_opacity (no snap)."""
    sb = _make_sidebar(allow_lan=False)
    anim = sb._lan_indicator.animate_opacity
    assert isinstance(anim, ft.Animation)
    assert anim.duration == 700
    assert anim.curve == ft.AnimationCurve.EASE_OUT


def test_lan_button_keeps_icon_visible_inside_stack():
    """The icon stays centered while the dot sits at the top-right corner."""
    sb = _make_sidebar(allow_lan=False)
    content = sb._lan_btn.content
    assert isinstance(content, ft.Stack)
    assert content.controls[0] is sb._lan_icon
    assert content.controls[1] is sb._lan_indicator
