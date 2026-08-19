"""Regression tests for TerminalWindow (Logs page).

Design spec: Minimal title 'Live Logs' (size=13, color=#94A3B8) and 3 sleek icon action buttons
(Stream toggle, Copy, Clear) in top-right corner.
"""

from __future__ import annotations

import flet as ft

from src.ui.components.logs.terminal_window import TerminalWindow


def _collect_controls(control, type_cls):
    """Recursively collect controls of a given type in a control tree."""
    found = []
    if isinstance(control, type_cls):
        found.append(control)
    for attr in ("content", "controls"):
        child = getattr(control, attr, None)
        if isinstance(child, ft.Control):
            found.extend(_collect_controls(child, type_cls))
        elif isinstance(child, list):
            for c in child:
                if isinstance(c, ft.Control):
                    found.extend(_collect_controls(c, type_cls))
    return found


def _make_window():
    log_text = ft.Text("log line")
    win = TerminalWindow(
        log_text_control=log_text,
        on_copy_click=lambda e: None,
        on_clear_click=lambda e: None,
    )
    return win, log_text


def test_terminal_title_minimal():
    """The title must be minimal (size=13, color=#94A3B8)."""
    win, _ = _make_window()
    texts = _collect_controls(win, ft.Text)
    title = [t for t in texts if t.value in ("Live Logs", "Console Output")]
    assert title, "minimal terminal title not found"
    assert title[0].size == 13
    assert title[0].color == "#94A3B8"


def test_icon_action_bar_three_buttons():
    """Toolbar contains exactly 3 icon buttons: stream toggle, copy, clear."""
    win, _ = _make_window()
    icon_btns = _collect_controls(win, ft.IconButton)
    assert len(icon_btns) == 3
    assert win._toggle_tail_btn in icon_btns
    assert win._copy_btn in icon_btns
    assert win._clear_btn in icon_btns


def test_toggle_tail_icon_swap():
    """Toggling stream updates the icon between play and pause."""
    win, _ = _make_window()
    assert win._toggle_tail_btn.icon == ft.Icons.PLAY_ARROW_ROUNDED
    win._on_toggle_handler(None)
    assert win._tailing_enabled is True
    assert win._toggle_tail_btn.icon == ft.Icons.PAUSE_ROUNDED
    win._on_toggle_handler(None)
    assert win._tailing_enabled is False
    assert win._toggle_tail_btn.icon == ft.Icons.PLAY_ARROW_ROUNDED
