"""Add server/subscription dialog components."""

from __future__ import annotations

from typing import Callable, Optional
from urllib.parse import urlparse

import flet as ft

from src.core.i18n import t
from src.utils.link_parser import LinkParser


class AddServerDialog(ft.AlertDialog):
    """Standard, border-enclosed AlertDialog for adding servers or subscription links."""

    def __init__(
        self,
        on_server_added: Callable[[str, dict], None],
        on_subscription_added: Callable[[str, str], None],
        on_close: Callable,
        on_create_chain: Optional[Callable] = None,
    ):
        self._on_server_added = on_server_added
        self._on_subscription_added = on_subscription_added
        self._on_close = on_close
        self._on_create_chain = on_create_chain

        WHITE = ft.Colors.WHITE
        MUTED = ft.Colors.GREY_500
        ACCENT = "#A78BFA"

        title_control = ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.ADD_LINK_ROUNDED,
                    color=ACCENT,
                    size=20,
                ),
                ft.Text(
                    t("add_dialog.title", default="Add Server or Subscription"),
                    size=15,
                    weight=ft.FontWeight.BOLD,
                    color=WHITE,
                ),
            ],
            spacing=8,
        )

        # Single Clean Input Field with Prefix Margin Container
        self._content_input = ft.TextField(
            prefix=ft.Container(
                content=ft.Icon(ft.Icons.TERMINAL_ROUNDED, color=ACCENT, size=18),
                margin=ft.Margin.only(right=10, left=4),
            ),
            hint_text=t(
                "add_dialog.link_hint",
                default="Paste vless://, vmess://, ss:// or subscription URL",
            ),
            hint_style=ft.TextStyle(size=12, color=MUTED),
            bgcolor="#1A1B26",
            border_color=ft.Colors.with_opacity(0.25, "#7C3AED"),
            focused_border_color="#7C3AED",
            color=WHITE,
            cursor_color=ACCENT,
            text_size=12,
            height=46,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            autofocus=True,
            on_submit=self._handle_add,
        )

        self._cancel_btn = ft.TextButton(
            t("add_dialog.cancel", default="Cancel"),
            style=ft.ButtonStyle(
                color=ft.Colors.GREY_400,
                overlay_color=ft.Colors.with_opacity(0.1, WHITE),
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
                tight=True,  # Crucial: prevents ft.Row from expanding button to full width
            ),
            bgcolor="#6D28D9",
            color=WHITE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            ),
            on_click=self._handle_add,
        )

        actions = [self._cancel_btn, self._add_btn]

        super().__init__(
            modal=True,
            barrier_color=ft.Colors.with_opacity(0.7, ft.Colors.BLACK),
            bgcolor="#12131C",
            shape=ft.RoundedRectangleBorder(
                radius=16,
                side=ft.BorderSide(1.5, ft.Colors.with_opacity(0.3, "#7C3AED")),
            ),
            title=title_control,
            content=ft.Container(
                width=400,  # Comfortable fixed width
                content=ft.Column(
                    controls=[
                        self._content_input,
                    ],
                    tight=True,
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,  # Forces TextField to stretch across full width
                ),
            ),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
            actions_padding=ft.Padding.only(right=16, bottom=16, left=16),
        )

    def _handle_add(self, e=None):
        """Handle the add button click. Supports single/multiple server links or subscription URLs."""
        content = self._content_input.value.strip() if self._content_input.value else ""
        self._content_input.error_text = None

        if not content:
            self._content_input.error_text = t("add_dialog.required", default="Configuration link or URL required")
            try:
                self._content_input.update()
            except Exception:
                pass
            return

        lines = content.splitlines()
        valid_configs = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith(
                (
                    "vless://",
                    "vmess://",
                    "trojan://",
                    "ss://",
                    "hysteria2://",
                    "tuic://",
                    "socks://",
                )
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
            self._on_server_added(parsed["name"], parsed["config"])
            self._reset_and_close()
            return

        # Try parsing direct link
        try:
            parsed = LinkParser.parse_link(content)
            self._on_server_added(parsed["name"], parsed["config"])
            self._reset_and_close()
            return
        except Exception:
            pass

        # Subscription URL handling
        if content.startswith(("http://", "https://")):
            parsed_url = urlparse(content)
            sub_name = parsed_url.netloc or "Subscription"
            if len(sub_name) > 30:
                sub_name = sub_name[:30] + "..."
            sub_name = f"Sub ({sub_name})"
            self._on_subscription_added(sub_name, content)
            self._reset_and_close()
            return

        self._content_input.error_text = t("add_dialog.invalid_link", default="Invalid server link or subscription URL")
        try:
            self._content_input.update()
        except Exception:
            pass

    def _show_success(self, msg: str):
        """Show a success message via toast."""
        if self.page and hasattr(self.page, "_toast_manager"):
            self.page._toast_manager.success(msg)

    def _handle_close(self, e):
        """Handle the cancel button click."""
        self._reset_and_close()

    def _reset_and_close(self):
        """Reset field and close the dialog."""
        self._content_input.value = ""
        self._content_input.error_text = None
        self._on_close()

    def _show_error(self, msg: str):
        """Show an error message via toast."""
        if self.page and hasattr(self.page, "_toast_manager"):
            self.page._toast_manager.error(msg)


class AddServerModalContainer(ft.Container):
    """Custom in-page modal overlay for the Add Server/Subscription dialog.

    Lives as the TOP layer of the server list's ``ft.Stack`` (Layer 1). Toggling
    ``visible`` only repaints this container — the server list (Layer 0) and its
    ConfigCards are never touched, so opening/closing causes zero background
    flicker and never resets the neon inspection animations.

    Does NOT use ``page._dialogs`` / ``page.update()``.
    """

    def __init__(
        self,
        on_server_added: Callable[[str, dict], None],
        on_subscription_added: Callable[[str, str], None],
        on_close: Callable,
        on_create_chain: Optional[Callable] = None,
    ):
        self._on_server_added = on_server_added
        self._on_subscription_added = on_subscription_added
        self._on_close = on_close
        self._on_create_chain = on_create_chain

        WHITE = ft.Colors.WHITE
        MUTED = ft.Colors.GREY_500
        ACCENT = "#A78BFA"

        title_control = ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.ADD_LINK_ROUNDED,
                    color=ACCENT,
                    size=20,
                ),
                ft.Text(
                    t("add_dialog.title", default="Add Server or Subscription"),
                    size=15,
                    weight=ft.FontWeight.BOLD,
                    color=WHITE,
                ),
            ],
            spacing=8,
        )

        self._content_input = ft.TextField(
            prefix=ft.Container(
                content=ft.Icon(ft.Icons.TERMINAL_ROUNDED, color=ACCENT, size=18),
                margin=ft.Margin.only(right=10, left=4),
            ),
            hint_text=t(
                "add_dialog.link_hint",
                default="Paste vless://, vmess://, ss:// or subscription URL",
            ),
            hint_style=ft.TextStyle(size=12, color=MUTED),
            bgcolor="#1A1B26",
            border_color=ft.Colors.with_opacity(0.25, "#7C3AED"),
            focused_border_color="#7C3AED",
            color=WHITE,
            cursor_color=ACCENT,
            text_size=12,
            height=46,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            autofocus=True,
            on_submit=self._handle_add,
        )

        self._cancel_btn = ft.TextButton(
            t("add_dialog.cancel", default="Cancel"),
            style=ft.ButtonStyle(
                color=ft.Colors.GREY_400,
                overlay_color=ft.Colors.with_opacity(0.1, WHITE),
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
                tight=True,
            ),
            bgcolor="#6D28D9",
            color=WHITE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            ),
            on_click=self._handle_add,
        )

        actions = [self._cancel_btn, self._add_btn]

        card = ft.Container(
            content=ft.Column(
                controls=[
                    title_control,
                    self._content_input,
                    ft.Row(actions, alignment=ft.MainAxisAlignment.END, spacing=8),
                ],
                tight=True,
                spacing=18,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            width=420,
            bgcolor="#12131C",
            border_radius=16,
            border=ft.Border.all(1.5, ft.Colors.with_opacity(0.3, "#7C3AED")),
            padding=20,
        )

        super().__init__(
            expand=True,
            bgcolor=ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
            alignment=ft.Alignment.CENTER,
            content=card,
            visible=False,
        )

    def _handle_add(self, e=None):
        """Handle the add button click. Supports single/multiple links or a subscription URL."""
        content = self._content_input.value.strip() if self._content_input.value else ""
        self._content_input.error_text = None

        if not content:
            self._content_input.error_text = t("add_dialog.required", default="Configuration link or URL required")
            try:
                self._content_input.update()
            except Exception:
                pass
            return

        lines = content.splitlines()
        valid_configs = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith(
                (
                    "vless://",
                    "vmess://",
                    "trojan://",
                    "ss://",
                    "hysteria2://",
                    "tuic://",
                    "socks://",
                )
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
            self._on_server_added(parsed["name"], parsed["config"])
            self._reset_and_close()
            return

        # Try parsing direct link
        try:
            parsed = LinkParser.parse_link(content)
            self._on_server_added(parsed["name"], parsed["config"])
            self._reset_and_close()
            return
        except Exception:
            pass

        # Subscription URL handling
        if content.startswith(("http://", "https://")):
            parsed_url = urlparse(content)
            sub_name = parsed_url.netloc or "Subscription"
            if len(sub_name) > 30:
                sub_name = sub_name[:30] + "..."
            sub_name = f"Sub ({sub_name})"
            self._on_subscription_added(sub_name, content)
            self._reset_and_close()
            return

        self._content_input.error_text = t("add_dialog.invalid_link", default="Invalid server link or subscription URL")
        try:
            self._content_input.update()
        except Exception:
            pass

    def _show_success(self, msg: str):
        """Show a success message via toast."""
        page = None
        try:
            page = self.page
        except (RuntimeError, AttributeError):
            page = None
        if page and hasattr(page, "_toast_manager"):
            page._toast_manager.success(msg)

    def _handle_close(self, e):
        """Handle the cancel button click."""
        self._reset_and_close()

    def _reset_and_close(self):
        """Reset field and close the modal."""
        self._content_input.value = ""
        self._content_input.error_text = None
        self._on_close()

    def _show_error(self, msg: str):
        """Show an error message via toast."""
        page = None
        try:
            page = self.page
        except (RuntimeError, AttributeError):
            page = None
        if page and hasattr(page, "_toast_manager"):
            page._toast_manager.error(msg)
