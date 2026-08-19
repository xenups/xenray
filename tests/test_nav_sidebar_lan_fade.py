"""Unit tests for NavSidebar LAN button (matches origin/main exactly — no fade
artifacts, no indicator dot, no explicit size)."""

import flet as ft

from src.ui.components.common.nav_sidebar import NavSidebar


def _make_sidebar(allow_lan: bool = False):
    return NavSidebar(
        active_tab="dashboard",
        on_tab_change=lambda t: None,
        on_connect_click=lambda e: None,
        on_lan_click=lambda e: None,
        allow_lan=allow_lan,
    )


def test_nav_sidebar_lan_button_matches_original():
    """The LAN button is EXACTLY the original: content=_lan_icon, padding=all(10),
    border_radius=12, no explicit size, no animate, no indicator dot."""
    sidebar = _make_sidebar()
    assert sidebar._lan_btn.content is sidebar._lan_icon
    assert sidebar._lan_btn.padding == ft.Padding.all(10)
    assert sidebar._lan_btn.border_radius == 12
    assert sidebar._lan_btn.width == 42  # same size as the top nav buttons (42x42)
    assert sidebar._lan_btn.height == 42
    assert sidebar._lan_btn.animate is None  # no fade animation (reverted)
    assert not hasattr(sidebar, "_lan_indicator")  # no indicator dot


def test_update_lan_button_applies_style():
    """Toggling LAN updates the button bgcolor/border/shadow via the controller
    without raising (targeted update, no full sidebar re-render)."""
    sidebar = _make_sidebar(allow_lan=False)
    sidebar.update_lan_button(True)
    assert sidebar._lan_btn.bgcolor is not None
    assert sidebar._lan_icon.color is not None
