"""Server list item component for individual server display."""
from __future__ import annotations

import json
from typing import Callable, Optional

import flet as ft

from src.core.i18n import t
from src.utils.link_parser import LinkParser


class ServerListItem(ft.Container):
    """A single server item in the server list with a simple popup menu."""

    def __init__(
        self,
        profile: dict,
        on_select: Callable[[dict], None],
        on_delete: Optional[Callable[[str], None]] = None,
        is_selected: bool = False,
        read_only: bool = False,
        cached_ping: Optional[tuple] = None,  # (text, color, latency_val)
    ):
        super().__init__()
        self.height = 65
        self._profile = profile
        self._on_select = on_select
        self._on_delete = on_delete
        self._read_only = read_only
        self._is_selected = is_selected

        # Extract data
        config = profile.get("config", {})
        address, port = self._extract_address_port(config)
        name = profile.get("name", "Unknown")

        # Determine protocol for display
        protocol = "unknown"
        for outbound in config.get("outbounds", []):
            if outbound.get("protocol") in [
                "vless",
                "vmess",
                "trojan",
                "shadowsocks",
                "hysteria2",
            ]:
                protocol = outbound.get("protocol").upper()
                break

        # Ping state
        last_ping = "..."
        last_ping_color = ft.Colors.GREY_500
        if cached_ping:
            last_ping, last_ping_color, _ = cached_ping
        elif profile.get("last_latency"):
            last_ping = profile["last_latency"]
            latency_val = profile.get("last_latency_val", 999999)
            last_ping_color = self._get_ping_color(latency_val)

        # Latency Widget
        self.latency_text = ft.Text(
            last_ping,
            size=11,
            color=last_ping_color if last_ping != "..." else ft.Colors.GREY_500,
            weight=ft.FontWeight.BOLD if last_ping != "..." else ft.FontWeight.NORMAL,
        )

        # Country Flag or Globe Icon
        country_code = profile.get("country_code")
        if country_code:
            flag_content = ft.Image(
                src=f"/flags/{country_code.lower()}.svg",
                width=28,
                height=28,
                fit=ft.BoxFit.COVER,
                gapless_playback=True,
                filter_quality=ft.FilterQuality.HIGH,
                error_content=ft.Icon(ft.Icons.PUBLIC, size=28, color=ft.Colors.GREY_400),
            )
        else:
            flag_content = ft.Icon(ft.Icons.PUBLIC, size=28, color=ft.Colors.GREY_400)

        self.flag_img = ft.Container(
            width=28,
            height=28,
            border_radius=14,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=flag_content,
            alignment=ft.Alignment.CENTER,
        )

        # Actions Menu
        menu_items = [
            ft.PopupMenuItem(
                content=ft.Text(t("server_list.share")),
                icon=ft.Icons.SHARE_ROUNDED,
                on_click=self._copy_config,
            ),
        ]
        if not read_only and on_delete:
            menu_items.append(
                ft.PopupMenuItem(
                    content=ft.Text(t("server_list.delete")),
                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                    on_click=self._delete_item,
                )
            )

        self.menu_button = ft.PopupMenuButton(
            items=menu_items,
            icon=ft.Icons.MORE_VERT_ROUNDED,
            icon_color=ft.Colors.GREY_400,
            icon_size=20,
        )

        # Middle Content
        middle_content = ft.Column(
            [
                ft.Text(
                    name,
                    weight=ft.FontWeight.BOLD,
                    size=14,
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.Text(
                    f"{protocol} | {address}:{port}",
                    size=11,
                    color=ft.Colors.GREY_500,
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
            spacing=2,
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )

        # Selection border logic
        border_side = ft.BorderSide(2, ft.Colors.BLUE) if is_selected else ft.BorderSide(1, ft.Colors.OUTLINE)

        # Main Layout
        from src.ui.helpers.gradient_helper import GradientHelper

        self.content = ft.Row(
            [
                ft.Container(content=self.flag_img, padding=ft.padding.only(left=5)),
                middle_content,
                ft.Column(
                    [self.latency_text],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=0,
                ),
                self.menu_button,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self.padding = ft.padding.symmetric(horizontal=10, vertical=8)
        self.bgcolor = "#121212"
        self.gradient = GradientHelper.get_flag_gradient(country_code)
        self.border = ft.border.all(color=border_side.color, width=border_side.width)
        self.border_radius = 8
        self.margin = ft.margin.symmetric(horizontal=10)  # Added to reduce width
        self.on_click = lambda e: self._on_select(self._profile)

    def _get_ping_color(self, val):
        if val < 1000:
            return ft.Colors.GREEN  # Increased threshold to 1000ms
        if val < 2000:
            return ft.Colors.ORANGE
        return ft.Colors.RED

    def _copy_config(self, e):
        """Share config link."""
        try:
            link = LinkParser.generate_link(self._profile.get("config", {}), self._profile.get("name", "server"))
            if not link:
                link = json.dumps(self._profile.get("config", {}), indent=2)

            if self.page:
                self.page.set_clipboard(link)
                # Use toast manager if available
                if hasattr(self.page, "_toast_manager"):
                    self.page._toast_manager.success(t("server_list.link_copied"), 2000)
                self.page.update()
        except Exception:
            # Silently fail if clipboard or link generation fails
            pass

    def _delete_item(self, e):
        """Delete item."""
        if self._on_delete:
            self._on_delete(self._profile["id"])

    def _extract_address_port(self, config: dict) -> tuple:
        """Extract server address and port from config."""
        outbounds = config.get("outbounds", [])
        for outbound in outbounds:
            protocol = outbound.get("protocol")
            if protocol in ["vless", "vmess", "trojan", "shadowsocks", "hysteria2"]:
                settings = outbound.get("settings", {})
                if "vnext" in settings and settings["vnext"]:
                    server = settings["vnext"][0]
                    return server.get("address", "Unknown"), server.get("port", "N/A")
                elif "servers" in settings and settings["servers"]:
                    server = settings["servers"][0]
                    return server.get("address", "Unknown"), server.get("port", "N/A")
        return "Unknown", "N/A"

    def update_ping(self, latency_str, color):
        """Update ping with pre-calculated color."""
        self.latency_text.value = latency_str
        self.latency_text.color = color
        self.latency_text.weight = ft.FontWeight.BOLD
        self.latency_text.update()

    def update_icon(self, code, name=""):
        if code:
            # Update to flag image
            self.flag_img.content = ft.Image(
                src=f"/flags/{code.lower()}.svg",
                width=28,
                height=28,
                fit=ft.BoxFit.COVER,
                gapless_playback=True,
                filter_quality=ft.FilterQuality.HIGH,
                error_content=ft.Icon(ft.Icons.PUBLIC, size=28, color=ft.Colors.GREY_400),
            )
            from src.ui.helpers.gradient_helper import GradientHelper

            self.gradient = GradientHelper.get_flag_gradient(code)
        else:
            # Update to globe icon
            self.flag_img.content = ft.Icon(ft.Icons.PUBLIC, size=28, color=ft.Colors.GREY_400)
            from src.ui.helpers.gradient_helper import GradientHelper

            self.gradient = GradientHelper.get_flag_gradient(None)

        self.flag_img.update()
        self.update()
