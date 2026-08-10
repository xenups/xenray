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
        MUTED = ft.Colors.GREY_500
        ACCENT = "#A78BFA"
        FIELD_BG = "#1A1B26"
        FIELD_BORDER = ft.Colors.with_opacity(0.15, "#7C3AED")

        title_control = ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.ADD_LINK_ROUNDED,
                    color=ACCENT,
                    size=22,
                ),
                ft.Text(
                    t("add_dialog.title", default="Add Server or Subscription"),
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=WHITE,
                ),
            ],
            spacing=8,
        )

        self._name_input = ft.TextField(
            hint_text=t(
                "add_dialog.name_hint",
                default="Name (Required for Subscriptions)",
            ),
            hint_style=ft.TextStyle(color=MUTED),
            prefix=ft.Icon(ft.Icons.LABEL_OUTLINE, color=ACCENT),
            border_color=FIELD_BORDER,
            bgcolor=FIELD_BG,
            color=WHITE,
            cursor_color=ACCENT,
            height=45,
            content_padding=10,
        )

        self._content_input = ft.TextField(
            hint_text=t(
                "add_dialog.link_hint",
                default="vless://... or https://example.com/sub",
            ),
            hint_style=ft.TextStyle(color=MUTED),
            prefix=ft.Icon(ft.Icons.TERMINAL_ROUNDED, color=ACCENT),
            border_color=FIELD_BORDER,
            bgcolor=FIELD_BG,
            color=WHITE,
            cursor_color=ACCENT,
            height=45,
            content_padding=10,
        )

        self._cancel_btn = ft.TextButton(
            t("add_dialog.cancel", default="Cancel"),
            style=ft.ButtonStyle(
                color=ft.Colors.GREY_400,
                overlay_color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
            ),
            on_click=self._handle_close,
        )

        self._add_btn = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CHECK, size=16, color=WHITE),
                    ft.Text(t("add_dialog.add", default="Add"), color=WHITE),
                ],
                spacing=4,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor="#6D28D9",
            color=WHITE,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            on_click=self._handle_add,
        )

        actions = [self._cancel_btn, self._add_btn]

        if on_create_chain:
            actions.insert(
                0,
                ft.TextButton(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.LINK_ROUNDED, size=15, color="#c084fc"),
                            ft.Text(
                                t("chain.title", default="Chain Builder"),
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color="#c084fc",
                            ),
                        ],
                        spacing=6,
                    ),
                    on_click=self._handle_create_chain,
                ),
            )

        super().__init__(
            modal=True,
            title=title_control,
            content=ft.Column(
                controls=[
                    self._name_input,
                    self._content_input,
                ],
                tight=True,
                spacing=12,
            ),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
            actions_padding=ft.Padding.only(right=16, bottom=16, left=16),
            bgcolor="#12131C",
            shape=ft.RoundedRectangleBorder(radius=16),
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

        self._name_input.error_text = None
        self._content_input.error_text = None

        if not content:
            self._content_input.error_text = t(
                "add_dialog.required", default="Configuration link or URL required"
            )
            self._content_input.update()
            return

        lines = content.splitlines()
        valid_configs = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith(
                ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://")
            ):
                try:
                    parsed = LinkParser.parse_link(line)
                    valid_configs.append(parsed)
                except Exception:
                    pass

        if len(valid_configs) > 1:
            for parsed in valid_configs:
                self._on_server_added(parsed["name"], parsed["config"])
            self._show_success(f"{len(valid_configs)} servers added!")
            self._reset_and_close()
            return

        if len(valid_configs) == 1:
            parsed = valid_configs[0]
            final_name = name if name else parsed["name"]
            self._on_server_added(final_name, parsed["config"])
            self._reset_and_close()
            return

        is_config_link = content.startswith(
            ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://")
        )

        if is_config_link:
            try:
                logger.debug(f"Attempting to parse config: {content[:50]}...")
                parsed = LinkParser.parse_link(content)
                final_name = name if name else parsed["name"]
                self._on_server_added(final_name, parsed["config"])
                self._reset_and_close()
                return
            except Exception as ex:
                logger.error(f"Failed to parse config: {ex}")
                error_msg = (
                    str(ex)
                    if str(ex)
                    else t("add_dialog.invalid_link", default="Invalid link format")
                )
                self._content_input.error_text = error_msg
                self._content_input.update()
                return

        if not name:
            self._name_input.error_text = t(
                "add_dialog.name_required", default="Subscription name required"
            )
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
