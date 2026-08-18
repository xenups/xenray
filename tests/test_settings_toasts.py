"""Tests for Settings notifications: toasts render for update flows + config
changes — including the drawer-not-mounted fallback path."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.ui.components.settings.settings_drawer import SettingsDrawer


def test_drawer_show_toast_uses_fallback_when_unmounted(monkeypatch):
    """Before the drawer is mounted (safe_page None), toasts must fall back to
    the always-alive MainWindow toast instead of being silently dropped."""
    drawer = SettingsDrawer.__new__(SettingsDrawer)
    fallback = MagicMock()
    drawer._fallback_toast = fallback
    # Unmounted drawer: safe_page returns None
    monkeypatch.setattr(SettingsDrawer, "safe_page", property(lambda self: None))

    drawer._show_toast("Update ready", "success")

    fallback.assert_called_once_with("Update ready", "success")


def test_drawer_show_toast_no_fallback_no_crash(monkeypatch):
    """Without a fallback AND without a page, _show_toast must not raise."""
    drawer = SettingsDrawer.__new__(SettingsDrawer)
    drawer._fallback_toast = None
    monkeypatch.setattr(SettingsDrawer, "safe_page", property(lambda self: None))

    drawer._show_toast("Silent", "info")  # must not raise


def test_mode_change_fires_toast():
    """handle_mode_change must notify the user of the mode switch."""
    from src.ui.handlers.settings_handler import SettingsHandler

    handler = SettingsHandler.__new__(SettingsHandler)
    toast = MagicMock()
    handler._show_toast = toast
    handler._on_mode_changed = MagicMock()

    class FakeRow:
        value = True  # proxy

    handler.handle_mode_change(FakeRow(), e=None)

    toast.assert_called_once()
    assert toast.call_args[0][1] == "success"
