"""Add server/subscription dialog component with i18n support."""
from __future__ import annotations

from typing import Callable

import flet as ft
from loguru import logger

from src.core.i18n import t
from src.utils.link_parser import LinkParser


class AddServerDialog(ft.AlertDialog):
    """Dialog for adding a server or subscription."""

    def __init__(
        self,
        on_server_added: Callable[[str, dict], None],
        on_subscription_added: Callable[[str, str], None],
        on_close: Callable,
        on_create_chain: Callable = None,
    ):
        self._on_server_added = on_server_added
        self._on_subscription_added = on_subscription_added
        self._on_close = on_close
        self._on_create_chain = on_create_chain

        self._name_input = ft.TextField(
            label=t("add_dialog.name_label"),
            hint_text=t("add_dialog.name_hint"),
            text_size=13,
        )
        self._content_input = ft.TextField(
            label=t("add_dialog.link_label"),
            hint_text=t("add_dialog.link_hint"),
            multiline=True,
            min_lines=6,
            max_lines=6,
            text_size=13,
        )

        super().__init__(
            title=ft.Text(t("add_dialog.title"), size=18, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    [self._name_input, self._content_input],
                    spacing=15,
                    tight=True,
                ),
                width=450,
            ),
            actions=[
                ft.Row(
                    [
                        ft.TextButton(
                            t("chain.title"),
                            icon=ft.Icons.LINK,
                            on_click=self._handle_create_chain,
                            visible=bool(on_create_chain),
                        ),
                        ft.Container(expand=True),  # Spacer pushes right buttons
                        ft.TextButton(t("add_dialog.cancel"), on_click=self._handle_close),
                        ft.TextButton(t("add_dialog.add"), on_click=self._handle_add),
                    ],
                    expand=True,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def _handle_create_chain(self, e):
        """Handle create chain button click."""
        if self._on_create_chain:
            self._on_close()
            self._on_create_chain()

    def _handle_add(self, e):
        """Handle the add button click. Supports multiple configs separated by newlines."""
        content = self._content_input.value.strip() if self._content_input.value else ""
        name = self._name_input.value.strip() if self._name_input.value else ""

        # Reset errors
        self._name_input.error_text = None
        self._content_input.error_text = None

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
            self._show_success(f"{len(valid_configs)} servers added!")
            self._reset_and_close()
            return

        # Single config case
        if len(valid_configs) == 1:
            parsed = valid_configs[0]
            final_name = name if name else parsed["name"]
            self._on_server_added(final_name, parsed["config"])
            self._reset_and_close()
            return

        # If no valid configs found, check if entire content is a single config
        is_config_link = content.startswith(("vless://", "vmess://", "trojan://", "ss://", "hysteria2://"))

        if is_config_link:
            # Try to parse as config
            try:
                logger.debug(f"Attempting to parse config: {content[:50]}...")
                parsed = LinkParser.parse_link(content)
                final_name = name if name else parsed["name"]
                self._on_server_added(final_name, parsed["config"])
                self._reset_and_close()
                return
            except Exception as ex:
                # Show actual error for debugging
                logger.error(f"Failed to parse config: {ex}")
                error_msg = str(ex) if str(ex) else t("add_dialog.invalid_link")
                self._content_input.error_text = error_msg
                self._content_input.update()
                return

        # Not a config link, treat as subscription URL
        if not name:
            self._name_input.error_text = t("add_dialog.name_required")
            self._name_input.update()
            return

        self._on_subscription_added(name, content)
        self._reset_and_close()

    def _show_success(self, msg: str):
        """Show a success message via toast."""
        if self.page and hasattr(self.page, "_toast_manager"):
            self.page._toast_manager.success(msg)

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
        """Show an error message via toast."""
        if self.page and hasattr(self.page, "_toast_manager"):
            self.page._toast_manager.error(msg)
