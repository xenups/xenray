"""Server list item component for individual server display."""
from __future__ import annotations

from typing import Callable, Optional

import flet as ft


class ServerListItem(ft.Container):
    """A single server item in the server list."""

    def __init__(
        self,
        profile: dict,
        on_select: Callable[[dict], None],
        on_delete: Optional[Callable[[str], None]] = None,
        is_selected: bool = False,
        read_only: bool = False,
        cached_ping: Optional[tuple] = None,  # (text, color, latency_val)
    ):
        self._profile = profile
        self._on_select = on_select
        self._on_delete = on_delete
        self._read_only = read_only

        # Extract data
        config = profile.get("config", {})
        address, port = self._extract_address_port(config)
        pid = profile.get("id")

        # Ping state from cache or profile
        last_ping = "..."
        last_ping_color = ft.Colors.GREY_500

        if cached_ping:
            last_ping, last_ping_color, _ = cached_ping
        elif profile.get("last_latency"):
            last_ping = profile["last_latency"]
            latency_val = profile.get("last_latency_val", 999999)
            if latency_val < 1000:
                last_ping_color = ft.Colors.GREEN_400
            elif latency_val < 2000:
                last_ping_color = ft.Colors.ORANGE_400
            else:
                last_ping_color = ft.Colors.RED_400

        # Selection styling
        if is_selected:
            border_color = ft.Colors.PRIMARY
            border_width = 2
            bg_color = ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY)
        else:
            border_color = (
                ft.Colors.with_opacity(0.5, ft.Colors.OUTLINE_VARIANT)
                if read_only
                else ft.Colors.OUTLINE_VARIANT
            )
            border_width = 1
            bg_color = ft.Colors.SURFACE

        # Ping label (exposed for updates)
        self.ping_label = ft.Text(
            last_ping, size=12, color=last_ping_color, weight=ft.FontWeight.BOLD
        )

        # Icon container (exposed for flag updates)
        icon_content = self._create_icon_content(profile)
        self.icon_container = ft.Container(
            content=icon_content,
            width=28,
            height=28,
            border_radius=14,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
            alignment=ft.alignment.center,
            tooltip=profile.get("country_name") or profile.get("country_code") or "",
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=3,
                color=ft.Colors.with_opacity(0.15, ft.Colors.BLACK),
                offset=ft.Offset(0, 1),
            ),
        )

        # Left content
        left_content = ft.Row(
            [
                self.icon_container,
                ft.Column(
                    [
                        ft.Text(
                            profile["name"],
                            weight=ft.FontWeight.BOLD,
                            size=14,
                            color=ft.Colors.ON_SURFACE,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            f"{address}:{port}",
                            size=11,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=2,
                ),
            ],
            spacing=10,
            expand=True,
        )

        # Right content
        right_controls = [self.ping_label]
        if not read_only and on_delete:
            right_controls.append(
                ft.IconButton(
                    ft.Icons.DELETE,
                    icon_color=ft.Colors.RED_400,
                    tooltip="Delete Server",
                    on_click=lambda e: on_delete(pid),
                )
            )
        right_content = ft.Row(
            right_controls, spacing=5, alignment=ft.MainAxisAlignment.END
        )

        super().__init__(
            content=ft.Row(
                [left_content, right_content],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
            border_radius=8,
            bgcolor=bg_color,
            border=ft.border.all(border_width, border_color),
            on_click=lambda e: on_select(profile),
            ink=True,
        )

    def _create_icon_content(self, profile: dict) -> ft.Control:
        """Create the flag or globe icon."""
        if profile.get("country_code"):
            return ft.Image(
                src=f"/flags/{profile['country_code'].lower()}.svg",
                width=28,
                height=28,
                fit=ft.ImageFit.COVER,
                gapless_playback=True,
                filter_quality=ft.FilterQuality.HIGH,
                border_radius=ft.border_radius.all(14),
                anti_alias=True,
            )
        return ft.Icon(ft.Icons.PUBLIC, size=14, color=ft.Colors.ON_SURFACE_VARIANT)

    def _extract_address_port(self, config: dict) -> tuple:
        """Extract server address and port from config."""
        outbounds = config.get("outbounds", [])
        for outbound in outbounds:
            protocol = outbound.get("protocol")
            if protocol in ["vless", "vmess", "trojan", "shadowsocks"]:
                settings = outbound.get("settings", {})
                if "vnext" in settings and settings["vnext"]:
                    server = settings["vnext"][0]
                    return server.get("address", "Unknown"), server.get("port", "N/A")
                elif "servers" in settings and settings["servers"]:
                    server = settings["servers"][0]
                    return server.get("address", "Unknown"), server.get("port", "N/A")
        return "Unknown", "N/A"

    def update_ping(self, text: str, color):
        """Update the ping label."""
        self.ping_label.value = text
        self.ping_label.color = color
        try:
            self.ping_label.update()
        except Exception:
            pass

    def update_icon(self, country_code: str, country_name: str = ""):
        """Update the icon to show a flag."""
        if not self.page:
            return
        self.icon_container.content = ft.Image(
            src=f"/flags/{country_code.lower()}.svg",
            width=28,
            height=28,
            fit=ft.ImageFit.COVER,
            gapless_playback=True,
            filter_quality=ft.FilterQuality.HIGH,
            border_radius=ft.border_radius.all(14),
            anti_alias=True,
        )
        self.icon_container.tooltip = country_name or country_code
        try:
            self.icon_container.update()
        except Exception:
            pass
