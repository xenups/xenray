"""Unit tests for system clipboard integration and paste functionality."""

from __future__ import annotations

from src.ui.components.servers.add_server_dialog import AddServerDialog, AddServerModalContainer
from src.utils.clipboard import get_clipboard_text


def test_get_clipboard_text_returns_string():
    """Verify get_clipboard_text always safely returns a string."""
    res = get_clipboard_text()
    assert isinstance(res, str)


def test_add_server_dialog_paste_integration(monkeypatch):
    """Verify clicking Paste button fills the input field from clipboard."""
    test_link = "vless://test-uuid@example.com:443?security=reality#TestServer"
    monkeypatch.setattr("src.ui.components.servers.add_server_dialog.get_clipboard_text", lambda: test_link)

    dialog = AddServerDialog(
        on_server_added=lambda name, cfg: None,
        on_subscription_added=lambda name, url: None,
        on_close=lambda: None,
    )

    assert dialog._content_input.value is None or dialog._content_input.value == ""

    # Trigger paste handler
    dialog._handle_paste(None)

    assert dialog._content_input.value == test_link
    assert dialog._content_input.error_text is None


def test_add_server_modal_container_paste_integration(monkeypatch):
    """Verify AddServerModalContainer Paste button fills the input field."""
    test_url = "https://example.com/sub/my-configs"
    monkeypatch.setattr("src.ui.components.servers.add_server_dialog.get_clipboard_text", lambda: test_url)

    modal = AddServerModalContainer(
        on_server_added=lambda name, cfg: None,
        on_subscription_added=lambda name, url: None,
        on_close=lambda: None,
    )

    assert modal._content_input.value is None or modal._content_input.value == ""

    # Trigger paste handler
    modal._handle_paste(None)

    assert modal._content_input.value == test_url
    assert modal._content_input.error_text is None
