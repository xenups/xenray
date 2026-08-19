"""Add server/subscription dialog components."""

from __future__ import annotations

from typing import Callable, Optional
from urllib.parse import urlparse

import flet as ft

from src.core.i18n import t
from src.utils.clipboard import get_clipboard_text
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
        MUTED = "#94A3B8"
        ACCENT = "#A78BFA"

        title_control = ft.Text(
            t("add_dialog.title", default="Add Server"),
            size=16,
            weight=ft.FontWeight.W_300,
            color=WHITE,
            style=ft.TextStyle(letter_spacing=0.6),
        )

        # Single Clean Input Field with Paste suffix button
        self._content_input = ft.TextField(
            hint_text=t(
                "add_dialog.link_hint",
                default="Paste vless://, vmess://, ss:// or subscription URL",
            ),
            hint_style=ft.TextStyle(size=12, color=MUTED, weight=ft.FontWeight.W_300),
            suffix=ft.IconButton(
                icon=ft.Icons.PASTE_ROUNDED,
                icon_color=ACCENT,
                icon_size=18,
                tooltip=t("add_dialog.paste", default="Paste from clipboard"),
                on_click=self._handle_paste,
            ),
            bgcolor=ft.Colors.with_opacity(0.05, WHITE),
            border_color=ft.Colors.with_opacity(0.08, WHITE),
            focused_border_color=ft.Colors.with_opacity(0.50, "#A855F7"),
            color=WHITE,
            cursor_color=ACCENT,
            text_size=12,
            height=44,
            border_radius=10,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            autofocus=True,
            on_submit=self._handle_add,
        )

        self._cancel_btn = ft.TextButton(
            t("add_dialog.cancel", default="Cancel"),
            style=ft.ButtonStyle(
                color=MUTED,
            ),
            on_click=self._handle_close,
        )

        self._add_btn = ft.OutlinedButton(
            content=ft.Text(
                t("add_dialog.add", default="Add"),
                size=13,
                weight=ft.FontWeight.W_400,
                color=WHITE,
            ),
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.with_opacity(0.20, "#A855F7"),
                side=ft.BorderSide(1.0, ft.Colors.with_opacity(0.50, "#A855F7")),
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.Padding.symmetric(horizontal=18, vertical=8),
            ),
            on_click=self._handle_add,
        )

        actions = [self._cancel_btn, self._add_btn]

        super().__init__(
            modal=True,
            barrier_color=ft.Colors.with_opacity(0.7, ft.Colors.BLACK),
            bgcolor=ft.Colors.with_opacity(0.95, "#141023"),
            shape=ft.RoundedRectangleBorder(
                radius=18,
                side=ft.BorderSide(1.0, ft.Colors.with_opacity(0.08, WHITE)),
            ),
            title=title_control,
            content=ft.Container(
                width=420,
                content=ft.Column(
                    controls=[
                        self._content_input,
                    ],
                    tight=True,
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
            actions_padding=ft.Padding.only(right=16, bottom=16, left=16),
        )

    def _handle_paste(self, e=None) -> None:
        """Paste text from clipboard directly into the input field."""
        try:
            clip_text = get_clipboard_text()
            if not clip_text and hasattr(self, "page") and self.page:
                try:
                    clip_text = self.page.get_clipboard()
                except Exception:
                    pass
            if clip_text:
                self._content_input.value = clip_text
                self._content_input.error_text = None
                try:
                    if self._content_input.page:
                        self._content_input.update()
                    elif hasattr(self, "page") and self.page:
                        self.page.update()
                except Exception:
                    pass
        except Exception:
            pass

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
        MUTED = "#94A3B8"
        ACCENT = "#A78BFA"

        title_control = ft.Text(
            t("add_dialog.title", default="Add Server"),
            size=16,
            weight=ft.FontWeight.W_300,
            color=WHITE,
            style=ft.TextStyle(letter_spacing=0.6),
        )

        self._content_input = ft.TextField(
            hint_text=t(
                "add_dialog.link_hint",
                default="Paste vless://, vmess://, ss:// or subscription URL",
            ),
            hint_style=ft.TextStyle(size=12, color=MUTED, weight=ft.FontWeight.W_300),
            suffix=ft.IconButton(
                icon=ft.Icons.PASTE_ROUNDED,
                icon_color=ACCENT,
                icon_size=18,
                tooltip=t("add_dialog.paste", default="Paste from clipboard"),
                on_click=self._handle_paste,
            ),
            bgcolor=ft.Colors.with_opacity(0.05, WHITE),
            border_color=ft.Colors.with_opacity(0.08, WHITE),
            focused_border_color=ft.Colors.with_opacity(0.50, "#A855F7"),
            color=WHITE,
            cursor_color=ACCENT,
            text_size=12,
            height=44,
            border_radius=10,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            autofocus=True,
            on_submit=self._handle_add,
        )

        self._cancel_btn = ft.TextButton(
            t("add_dialog.cancel", default="Cancel"),
            style=ft.ButtonStyle(
                color=MUTED,
            ),
            on_click=self._handle_close,
        )

        self._add_btn = ft.OutlinedButton(
            content=ft.Text(
                t("add_dialog.add", default="Add"),
                size=13,
                weight=ft.FontWeight.W_400,
                color=WHITE,
            ),
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.with_opacity(0.20, "#A855F7"),
                side=ft.BorderSide(1.0, ft.Colors.with_opacity(0.50, "#A855F7")),
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.Padding.symmetric(horizontal=18, vertical=8),
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
            bgcolor=ft.Colors.with_opacity(0.95, "#141023"),
            border_radius=18,
            border=ft.Border.all(1.0, ft.Colors.with_opacity(0.08, WHITE)),
            padding=20,
        )

        super().__init__(
            expand=True,
            bgcolor=ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
            alignment=ft.Alignment.CENTER,
            content=card,
            visible=False,
        )

    def _handle_paste(self, e=None) -> None:
        """Paste text from clipboard directly into the input field."""
        try:
            clip_text = get_clipboard_text()
            if not clip_text and hasattr(self, "page") and self.page:
                try:
                    clip_text = self.page.get_clipboard()
                except Exception:
                    pass
            if clip_text:
                self._content_input.value = clip_text
                self._content_input.error_text = None
                try:
                    if self._content_input.page:
                        self._content_input.update()
                    elif hasattr(self, "page") and self.page:
                        self.page.update()
                except Exception:
                    pass
        except Exception:
            pass

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
