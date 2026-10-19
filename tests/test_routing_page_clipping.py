"""Tests ensuring RoutingPage and view container enforce clip_behavior to prevent sidebar overflow."""

from __future__ import annotations

from unittest.mock import MagicMock

import flet as ft

from src.ui.pages.routing_page import RoutingPage


def test_routing_page_and_tabbarview_clipping() -> None:
    """RoutingPage and TabBarView must enforce HARD_EDGE clip_behavior so tab sliding never overflows sidebar."""
    mock_app_context = MagicMock()
    mock_app_context.routing.load_rules.return_value = {}
    mock_app_context.routing.load_toggles.return_value = {}

    page = RoutingPage(app_context=mock_app_context, on_back=lambda: None)

    # 1. RoutingPage container must have clip_behavior = HARD_EDGE
    assert page.clip_behavior == ft.ClipBehavior.HARD_EDGE

    # 2. TabBarView inside _tabs must also have clip_behavior = HARD_EDGE
    tab_bar_view = None
    if hasattr(page, "_tabs") and page._tabs.content:
        for ctrl in page._tabs.content.controls:
            if isinstance(ctrl, ft.TabBarView):
                tab_bar_view = ctrl
                break

    assert tab_bar_view is not None, "TabBarView not found in RoutingPage._tabs"
    assert tab_bar_view.clip_behavior == ft.ClipBehavior.HARD_EDGE
