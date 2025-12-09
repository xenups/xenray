"""Add server/subscription dialog component."""
from __future__ import annotations
from typing import Callable, Optional
import flet as ft

from src.utils.link_parser import LinkParser


class AddServerDialog(ft.AlertDialog):
    """Dialog for adding a server or subscription."""

    def __init__(
        self,
        on_server_added: Callable[[str, dict], None],  # (name, config) -> None
        on_subscription_added: Callable[[str, str], None],  # (name, url) -> None
        on_close: Callable,
    ):
        self._on_server_added = on_server_added
        self._on_subscription_added = on_subscription_added
        self._on_close = on_close
        
        self._name_input = ft.TextField(
            label="Name (Optional for Config)",
            hint_text="Required for Subscriptions",
            text_size=12,
        )
        self._content_input = ft.TextField(
            label="Link / URL",
            hint_text="vless://... or https://example.com/sub",
            multiline=True,
            min_lines=3,
            max_lines=10,
            text_size=12,
        )
        
        super().__init__(
            title=ft.Text("Add Server or Subscription"),
            content=ft.Column(
                [self._name_input, self._content_input],
                height=180,
            ),
            actions=[
                ft.TextButton("Add", on_click=self._handle_add),
                ft.TextButton("Cancel", on_click=self._handle_close),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def _handle_add(self, e):
        """Handle the add button click."""
        content = self._content_input.value.strip()
        name = self._name_input.value.strip()
        
        if not content:
            self._content_input.error_text = "Required"
            self._content_input.update()
            return
        
        # Try to parse as server link
        is_config = content.startswith(("vless://", "vmess://", "trojan://", "ss://"))
        
        try:
            parsed = LinkParser.parse_vless(content)
            final_name = name if name else parsed["name"]
            self._on_server_added(final_name, parsed["config"])
            self._reset_and_close()
            return
        except Exception:
            pass
        
        # Fall back to subscription
        if not name:
            self._name_input.error_text = "Name required for Subscription"
            self._name_input.update()
            if is_config:
                # Show that it's an invalid server link
                self._show_error("Invalid Server Link")
            return
        
        self._on_subscription_added(name, content)
        self._reset_and_close()

    def _handle_close(self, e):
        """Handle the cancel button click."""
        self._reset_and_close()

    def _reset_and_close(self):
        """Reset fields and close the dialog."""
        self._name_input.value = ""
        self._content_input.value = ""
        self._name_input.error_text = None
        self._content_input.error_text = None
        self._on_close()

    def _show_error(self, msg: str):
        """Show an error message via snackbar."""
        if self.page:
            self.page.open(ft.SnackBar(content=ft.Text(msg, color=ft.Colors.RED_400)))
            self.page.update()
