"""Tests for the START/STOP tailing button visibility in the Logs drawer.

The button must be unmissable: a filled, high-contrast control (green Start /
red Stop) with white text, a full-width row, and an icon+label swap on toggle.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import flet as ft

from src.ui.components.logs.log_viewer import LogViewer

OFF_BG = "#4ADE80"  # green — Start (invites the click)
ON_BG = "#f43f5e"  # red — Stop (unmissable while tailing)


def _make_drawer():
    """Build a LogsDrawer with a real LogViewer and mocked heartbeat."""
    lv = LogViewer("test")
    lv.start_tailing = MagicMock()
    lv.stop_tailing = MagicMock()
    drawer = __import__("src.ui.components.logs.logs_drawer", fromlist=["LogsDrawer"]).LogsDrawer(
        log_viewer=lv, heartbeat=MagicMock()
    )
    return drawer, lv


def _button_label(btn) -> str:
    """Extract the label text from the button's content Row."""
    assert isinstance(btn.content, ft.Row), "button content must be a Row"
    texts = [c for c in btn.content.controls if isinstance(c, ft.Text)]
    assert texts, "button content Row must contain a Text label"
    return texts[0].value


def _button_icon(btn) -> str:
    """Extract the icon name from the button's content Row."""
    assert isinstance(btn.content, ft.Row), "button content must be a Row"
    icons = [c for c in btn.content.controls if isinstance(c, ft.Icon)]
    assert icons, "button content Row must contain an Icon"
    return icons[0].icon


def test_toggle_btn_has_explicit_high_contrast_bgcolor():
    """The button must carry an explicit bgcolor (never theme-default)."""
    drawer, _ = _make_drawer()
    btn = drawer._toggle_tail_btn

    assert btn.style is not None
    assert btn.style.bgcolor is not None, "button must have an explicit bgcolor"
    assert btn.style.color == ft.Colors.WHITE, "button text must be white"
    # Initial (OFF) state must be the inviting green.
    assert btn.style.bgcolor == OFF_BG


def test_toggle_btn_initial_state_is_start():
    """Initial state: 'Start' label + PLAY icon + green bgcolor."""
    drawer, _ = _make_drawer()
    btn = drawer._toggle_tail_btn

    assert _button_label(btn) == "Start"
    assert _button_icon(btn) == ft.Icons.PLAY_CIRCLE_OUTLINE
    assert btn.style.bgcolor == OFF_BG


def test_toggle_swaps_to_stop_state():
    """After enabling: 'Stop' label + STOP icon + red bgcolor."""
    drawer, _ = _make_drawer()

    drawer._toggle_tailing(MagicMock(control=MagicMock()))
    btn = drawer._toggle_tail_btn

    assert _button_label(btn) == "Stop"
    assert _button_icon(btn) == ft.Icons.STOP_CIRCLE_OUTLINED
    assert btn.style.bgcolor == ON_BG


def test_toggle_swaps_back_to_start_state():
    """Toggling twice returns to 'Start' + PLAY icon + green bgcolor."""
    drawer, _ = _make_drawer()

    drawer._toggle_tailing(MagicMock(control=MagicMock()))
    drawer._toggle_tailing(MagicMock(control=MagicMock()))
    btn = drawer._toggle_tail_btn

    assert _button_label(btn) == "Start"
    assert _button_icon(btn) == ft.Icons.PLAY_CIRCLE_OUTLINE
    assert btn.style.bgcolor == OFF_BG


def test_toggle_btn_label_is_14_bold():
    """The Start/Stop button label must be size=14 bold — NOT shrunk."""
    drawer, _ = _make_drawer()
    btn = drawer._toggle_tail_btn
    assert isinstance(btn.content, ft.Row)
    texts = [c for c in btn.content.controls if isinstance(c, ft.Text)]
    assert texts, "button content Row must contain a Text label"
    label = texts[0]
    assert label.size == 14
    assert label.weight == ft.FontWeight.BOLD
    # No ButtonStyle text_style override may shrink the label.
    assert getattr(btn.style, "text_style", None) is None


def test_tail_row_is_full_width_and_button_same_size_class():
    """The tail row must be full-width; the button is height=32 (uniform with
    sibling buttons) and must NOT expand (uniform, not oversized)."""
    drawer, _ = _make_drawer()

    assert drawer._tail_row.expand is True, "tail row must be full-width (expand=True)"
    assert drawer._toggle_tail_btn in drawer._tail_row.controls
    assert drawer._toggle_tail_btn.height == 32, "button must be height=32 like siblings"
    assert drawer._toggle_tail_btn.expand is None, "button must NOT expand (uniform size)"
    shape = drawer._toggle_tail_btn.style.shape
    assert shape is not None and shape.radius == 8, "button radius must be 8 like siblings"
