"""Font-size regression tests for TerminalWindow (Logs page).

The user flagged that button labels and the top title must NOT shrink.
Design spec: Copy/Clear labels size=11, title size=11. The Download button
was REMOVED (user request) and every action button shares one size class:
height=32, radius=8, explicit width so labels never resize them.
"""

from __future__ import annotations

import flet as ft

from src.ui.components.logs.terminal_window import TerminalWindow


def _collect_texts(control):
    """Recursively collect all ft.Text controls in a control tree."""
    found = []
    if isinstance(control, ft.Text):
        found.append(control)
    for attr in ("content", "controls"):
        child = getattr(control, attr, None)
        if isinstance(child, ft.Control):
            found.extend(_collect_texts(child))
        elif isinstance(child, list):
            for c in child:
                if isinstance(c, ft.Control):
                    found.extend(_collect_texts(c))
    return found


def _make_window():
    log_text = ft.Text("log line")
    win = TerminalWindow(
        log_text_control=log_text,
        on_copy_click=lambda e: None,
        on_clear_click=lambda e: None,
    )
    return win, log_text


def test_action_button_labels_not_shrunk():
    """Copy/Clear labels must be size=11 — NOT shrunk."""
    win, _ = _make_window()
    texts = _collect_texts(win)
    labels = {t.value: t for t in texts if t.value in ("Copy", "Clear")}
    assert set(labels) == {"Copy", "Clear"}, f"missing labels: {labels}"
    for label in labels.values():
        assert label.size == 11, f"'{label.value}' shrunk to size {label.size}"


def test_terminal_title_not_shrunk():
    """The 'XenRay CLI :: Main Logger' title must be size=11 — NOT shrunk."""
    win, _ = _make_window()
    texts = _collect_texts(win)
    titles = [t for t in texts if t.value.startswith("XENRAY_CLI")]
    assert titles, "terminal title text not found"
    assert titles[0].size == 11


def test_no_download_button():
    """The Download button was removed from the Logs tab toolbar."""
    win, _ = _make_window()
    texts = _collect_texts(win)
    labels = {t.value for t in texts if t.value in ("Download", "download", "دانلود", "Загрузка", "下载")}
    assert not labels, f"Download label still present: {labels}"
    # The toolbar Row must contain exactly Copy, Clear and the Start/Stop button.
    toolbar_rows = [
        c
        for c in win.content.controls
        if isinstance(c, ft.Row) and any(isinstance(b, ft.OutlinedButton) for b in c.controls)
    ]
    assert toolbar_rows, "toolbar Row not found"
    buttons = [b for row in toolbar_rows for b in row.controls]
    assert len(buttons) == 3, f"expected Copy/Clear/Start-Stop (3 buttons), got {len(buttons)}"
    assert all(isinstance(b, (ft.OutlinedButton, ft.FilledButton)) for b in buttons)


def test_action_buttons_uniform_size():
    """Copy/Clear/Start-Stop must share one size class: height=32, radius=8."""
    win, _ = _make_window()
    toolbar_rows = [
        c
        for c in win.content.controls
        if isinstance(c, ft.Row) and any(isinstance(b, ft.OutlinedButton) for b in c.controls)
    ]
    buttons = [b for row in toolbar_rows for b in row.controls]

    for btn in buttons:
        assert btn.height == 32, f"{btn} height {btn.height} != 32"
        assert btn.width is not None, f"{btn} has no explicit width (resize risk)"
        shape = btn.style.shape
        assert shape is not None and shape.radius == 8, f"{btn} radius != 8"
        assert getattr(btn.style, "text_style", None) is None, f"{btn} has text_style override"


def test_toggle_tail_button_visuals():
    """Start/Stop keeps its high-contrast filled identity (green Start / red Stop)."""
    win, _ = _make_window()
    btn = win._toggle_tail_btn
    assert isinstance(btn, ft.FilledButton)
    assert btn.style.bgcolor == "#4ADE80"
    assert btn.style.color == ft.Colors.WHITE
    assert btn.style.shape.radius == 8
