"""Add server/subscription dialog component matching Fluent Integrated UI/UX language."""
from __future__ import annotations

from typing import Callable

import flet as ft
from loguru import logger

from src.core.i18n import t
from src.ui.theme import AppColors
from src.utils.link_parser import LinkParser


class AddServerDialog(ft.AlertDialog):
    """Sleek Glassmorphism Dialog for adding servers, subscription links, or server chains."""

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

        WHITE = ft.Colors.WHITE

        # Header Title with Icon
        title_control = ft.Row(
            [
                ft.Container(
                    content=ft.Icon(ft.Icons.ADD_LINK_ROUNDED, size=20, color="#c084fc"),
                    padding=6,
                    border_radius=10,
                    bgcolor=ft.Colors.with_opacity(0.18, "#a855f7"),
                ),
                ft.Text(
                    t("add_dialog.title", default="Add Server or Subscription"),
                    size=16,
                    weight=ft.FontWeight.W_700,
                    color=WHITE,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Name Field
        self._name_input = ft.TextField(
            label=t("add_dialog.name_label", default="Server / Subscription Name (Optional)"),
            hint_text=t("add_dialog.name_hint", default="e.g. My Fast Server"),
            text_size=13,
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.18, "#130927"),
            border_color=ft.Colors.with_opacity(0.35, "#a855f7"),
            focused_border_color="#c084fc",
            cursor_color="#c084fc",
            prefix_icon=ft.Icons.LABEL_ROUNDED,
            focused_bgcolor=ft.Colors.with_opacity(0.25, "#180b33"),
        )

        # Config / Link Text Area Field
        self._content_input = ft.TextField(
            label=t("add_dialog.link_label", default="Config Link or Subscription URL"),
            hint_text=t(
                "add_dialog.link_hint",
                default="Paste vless://, vmess://, trojan://, ss://, hysteria2://, or https:// subscription URL...",
            ),
            multiline=True,
            min_lines=5,
            max_lines=5,
            text_size=12,
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.18, "#130927"),
            border_color=ft.Colors.with_opacity(0.35, "#a855f7"),
            focused_border_color="#c084fc",
            cursor_color="#c084fc",
            prefix_icon=ft.Icons.TERMINAL_ROUNDED,
            focused_bgcolor=ft.Colors.with_opacity(0.25, "#180b33"),
        )

        # Action Buttons
        self._cancel_btn = ft.Container(
            content=ft.Text(t("add_dialog.cancel", default="Cancel"), size=12, weight=ft.FontWeight.W_600, color=WHITE),
            padding=ft.Padding.symmetric(vertical=9, horizontal=16),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.1, WHITE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.2, WHITE)),
            on_click=self._handle_close,
            ink=True,
        )

        self._add_btn = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CHECK_ROUNDED, size=15, color=WHITE),
                    ft.Text(t("add_dialog.add", default="Add Server"), size=12, weight=ft.FontWeight.W_700, color=WHITE),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(vertical=9, horizontal=18),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.85, "#7c3aed"),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.8, "#c084fc")),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=16,
                color=ft.Colors.with_opacity(0.4, "#7c3aed"),
                offset=ft.Offset(0, 4),
            ),
            on_click=self._handle_add,
            ink=True,
        )

        chain_btn = (
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.LINK_ROUNDED, size=15, color="#c084fc"),
                        ft.Text(t("chain.title", default="Chain Builder"), size=12, weight=ft.FontWeight.W_600, color="#c084fc"),
                    ],
                    spacing=6,
                ),
                padding=ft.Padding.symmetric(vertical=9, horizontal=14),
                border_radius=10,
                bgcolor=ft.Colors.with_opacity(0.12, "#a855f7"),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.4, "#a855f7")),
                on_click=self._handle_create_chain,
                ink=True,
                visible=bool(on_create_chain),
            )
            if on_create_chain
            else ft.Container(visible=False)
        )

        actions_row = ft.Row(
            [
                chain_btn,
                ft.Container(expand=True),
                self._cancel_btn,
                self._add_btn,
            ],
            spacing=10,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        body_container = ft.Container(
            content=ft.Column(
                [
                    self._name_input,
                    self._content_input,
                    ft.Container(height=4),
                    actions_row,
                ],
                spacing=14,
                tight=True,
            ),
            width=480,
            padding=20,
            border_radius=18,
            bgcolor=ft.Colors.with_opacity(0.92, "#0d061c"),
            border=ft.Border.all(1.2, ft.Colors.with_opacity(0.5, "#a855f7")),
            shadow=ft.BoxShadow(
                spread_radius=2,
                blur_radius=32,
                color=ft.Colors.with_opacity(0.35, "#581c87"),
                offset=ft.Offset(0, 8),
            ),
        )

        super().__init__(
            title=title_control,
            content=body_container,
            bgcolor=ft.Colors.TRANSPARENT,
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
            self._content_input.error_text = t("add_dialog.required", default="Configuration link or URL required")
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
                logger.error(f"Failed to parse config: {ex}")
                error_msg = str(ex) if str(ex) else t("add_dialog.invalid_link", default="Invalid link format")
                self._content_input.error_text = error_msg
                self._content_input.update()
                return

        # Not a config link, treat as subscription URL
        if not name:
            self._name_input.error_text = t("add_dialog.name_required", default="Subscription name required")
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
