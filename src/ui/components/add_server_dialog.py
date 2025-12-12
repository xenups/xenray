"""Add server/subscription dialog component with i18n support."""
from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t
from src.utils.link_parser import LinkParser


class AddServerDialog(ft.AlertDialog):
    """Dialog for adding a server or subscription."""

    def __init__(
        self,
        on_server_added: Callable[[str, dict], None],
        on_subscription_added: Callable[[str, str], None],
        on_close: Callable,
    ):
        self._on_server_added = on_server_added
        self._on_subscription_added = on_subscription_added
        self._on_close = on_close

        self._name_input = ft.TextField(
            label=t("add_dialog.name_label"),
            hint_text=t("add_dialog.name_hint"),
            text_size=12,
        )
        self._content_input = ft.TextField(
            label=t("add_dialog.link_label"),
            hint_text=t("add_dialog.link_hint"),
            multiline=True,
            min_lines=3,
            max_lines=10,
            text_size=12,
        )

        super().__init__(
            title=ft.Text(t("add_dialog.title")),
            content=ft.Column(
                [self._name_input, self._content_input],
                width=400,
                spacing=10,
                tight=True,
            ),
            actions=[
                ft.TextButton(t("add_dialog.cancel"), on_click=self._handle_close),
                ft.TextButton(t("add_dialog.add"), on_click=self._handle_add),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def _handle_add(self, e):
        """Handle the add button click. Supports multiple configs separated by newlines."""
        content = self._content_input.value.strip()
        name = self._name_input.value.strip()

        if not content:
            self._content_input.error_text = t("add_dialog.required")
            self._content_input.update()
            return

        # Split by newlines to detect multi-config input
        lines = content.splitlines()
        valid_configs = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line is a config link
            if line.startswith(("vless://", "vmess://", "trojan://", "ss://", "hysteria2://")):
                try:
                    parsed = LinkParser.parse_link(line)
                    valid_configs.append(parsed)
                except Exception:
                    pass  # Skip invalid lines
        
        # If we found multiple configs, add them all
        if len(valid_configs) > 1:
            for parsed in valid_configs:
                self._on_server_added(parsed["name"], parsed["config"])
            self._show_success(f"{len(valid_configs)} servers added! 🚀")
            self._reset_and_close()
            return
        
        # Single config case
        if len(valid_configs) == 1:
            parsed = valid_configs[0]
            final_name = name if name else parsed["name"]
            self._on_server_added(final_name, parsed["config"])
            self._reset_and_close()
            return
        
        # If no valid configs found, try treating entire content as single config
        is_config = content.startswith(
            ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://")
        )
        
        try:
            parsed = LinkParser.parse_link(content)
            final_name = name if name else parsed["name"]
            self._on_server_added(final_name, parsed["config"])
            self._reset_and_close()
            return
        except Exception:
            pass

        # Treat as subscription URL
        if not name:
            self._name_input.error_text = t("add_dialog.name_required")
            self._name_input.update()
            if is_config:
                self._show_error(t("add_dialog.invalid_link"))
            return

        self._on_subscription_added(name, content)
        self._reset_and_close()
    
    def _show_success(self, msg: str):
        """Show a success message via snackbar."""
        if self.page:
            self.page.open(ft.SnackBar(content=ft.Text(msg, color=ft.Colors.GREEN_400)))
            self.page.update()

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
