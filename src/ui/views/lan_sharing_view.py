"""LAN Proxy Sharing View - full-page dedicated view with live QR code, settings state sync, and real-time toggle update."""

from __future__ import annotations

import base64
import io
import socket
from typing import Callable

import flet as ft

from src.core.i18n import get_language, t


def get_real_physical_lan_ip() -> str:
    """Detect actual physical LAN IP address, excluding TUN/TAP (10.0.0.x), loopback, and virtual adapters."""
    # Method 1: Hostname interface list scan prioritizing 192.168.x.x
    try:
        hostname = socket.gethostname()
        ip_list = socket.gethostbyname_ex(hostname)[2]

        valid_ips = []
        for ip in ip_list:
            # Exclude loopback, TUN default subnet (10.0.0.x), fake-ip ranges (198.18.x.x), link-local (169.254.x.x)
            if (
                ip.startswith("127.")
                or ip.startswith("10.0.0.")
                or ip.startswith("198.18.")
                or ip.startswith("169.254.")
            ):
                continue
            if ip.startswith("192.168."):
                return ip
            valid_ips.append(ip)

        if valid_ips:
            return valid_ips[0]
    except Exception:
        pass

    # Method 2: UDP probe to common gateway targets
    for target in ["192.168.1.1", "192.168.0.1", "1.1.1.1"]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect((target, 80))
            ip = s.getsockname()[0]
            s.close()
            if (
                not ip.startswith("127.")
                and not ip.startswith("10.0.0.")
                and not ip.startswith("198.18.")
                and not ip.startswith("169.254.")
            ):
                return ip
        except Exception:
            pass

    return "192.168.1.1"


# Alias for backward compatibility
get_real_local_ip = get_real_physical_lan_ip


def generate_qr_base64(data: str) -> str | None:
    """Generate QR code base64 string."""
    try:
        import qrcode  # noqa: PLC0415

        qr = qrcode.QRCode(version=1, box_size=5, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    except Exception:
        return None


class LanSharingView(ft.Container):
    """Dedicated full-page LAN Proxy Sharing view with real-time toggle updates."""

    def __init__(
        self,
        app_context=None,
        on_back: Callable | None = None,
        config_service=None,
        on_lan_toggle: Callable[[bool], None] | None = None,
    ):
        super().__init__()
        self.expand = True
        self.padding = 12

        self._app_context = app_context
        self._on_back = on_back
        self._on_lan_toggle = on_lan_toggle

        # Check RTL language
        self.is_rtl = get_language() == "fa"

        # Data: Real Local IP detection
        self.local_ip = get_real_local_ip()

        # Read ports and allow_lan directly from app settings
        try:
            self.http_port = (
                str(self._app_context.settings.get_http_port())
                if self._app_context and hasattr(self._app_context, "settings")
                else "10809"
            )
        except Exception:
            self.http_port = "10809"

        try:
            self.socks_port = (
                str(self._app_context.settings.get_proxy_port())
                if self._app_context and hasattr(self._app_context, "settings")
                else "10808"
            )
        except Exception:
            self.socks_port = "10808"

        try:
            self.allow_lan = (
                self._app_context.settings.get_allow_lan()
                if self._app_context and hasattr(self._app_context, "settings")
                else True
            )
        except Exception:
            self.allow_lan = True

        # ── Header Row with Master Switch ─────────────────────────────────────
        self._master_switch = ft.Switch(
            value=self.allow_lan,
            active_color="#4ADE80",
            on_change=self._on_toggle_change,
        )

        header_row = ft.Row(
            controls=[
                ft.Column(
                    [
                        ft.Text(
                            t("lan_sharing.title", default="LAN Proxy Sharing"),
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color="white",
                            rtl=self.is_rtl,
                        ),
                        ft.Text(
                            t(
                                "lan_sharing.subtitle",
                                default="Share your proxy connection across devices on your local network",
                            ),
                            size=11,
                            color="#8E8C99",
                            rtl=self.is_rtl,
                        ),
                    ],
                    spacing=2,
                ),
                self._master_switch,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # ── 1. Top Badges (IP & Ports) ───────────────────────────────────────
        self._ip_text_ctrl = ft.Text(
            self.local_ip,
            size=11,
            weight=ft.FontWeight.BOLD,
            color="white",
            selectable=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        def make_micro_chip(label_key: str, default_label: str, value: str, val_text_ctrl: ft.Text | None = None):
            val_ctrl = val_text_ctrl or ft.Text(
                value,
                size=11,
                weight=ft.FontWeight.BOLD,
                color="white",
                selectable=True,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
            return ft.Container(
                expand=1,
                bgcolor="#13141C",
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                border_radius=8,
                border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
                content=ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.COPY,
                            icon_size=14,
                            icon_color="#8B5CF6",
                            on_click=lambda e, v=value: self._copy(v),
                            style=ft.ButtonStyle(padding=ft.Padding.all(2)),
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    t(label_key, default=default_label),
                                    size=10,
                                    color="#8E8C99",
                                    weight=ft.FontWeight.W_500,
                                    rtl=self.is_rtl,
                                ),
                                val_ctrl,
                            ],
                            spacing=1,
                            expand=True,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )

        badges_row = ft.Row(
            controls=[
                make_micro_chip("lan_sharing.local_ip", "Local IP", self.local_ip, val_text_ctrl=self._ip_text_ctrl),
                make_micro_chip("lan_sharing.http_port", "HTTP Port", self.http_port),
                make_micro_chip("lan_sharing.socks_port", "SOCKS5 Port", self.socks_port),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=6,
        )

        # ── 2. QR Code Container ─────────────────────────────────────────────
        self._qr_box = ft.Container(
            width=170,
            height=170,
            border_radius=8,
            padding=4,
            alignment=ft.Alignment.CENTER,
        )
        self._update_qr_box(self.allow_lan)

        qr_card = ft.Container(
            bgcolor="#13141C",
            border_radius=10,
            padding=8,
            alignment=ft.Alignment.CENTER,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
            content=ft.Column(
                [
                    ft.Text(
                        t("lan_sharing.scan_to_connect", default="Scan to Connect"),
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color="white",
                        rtl=self.is_rtl,
                    ),
                    self._qr_box,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            ),
        )

        # ── 3. Bottom Guide Card (4 Connection Steps) ─────────────────────────
        step1_text = t(
            "lan_sharing.guide_step_1",
            default="1. Enable 'Allow Sharing' on your main Windows network adapter properties.",
        )
        step2_text = t(
            "lan_sharing.guide_step_2",
            default="2. Connect target device (phone, TV, or PC) to the same Wi-Fi network.",
        )
        step3_text = t(
            "lan_sharing.guide_step_3",
            default="3. Set Proxy to Manual mode on the target device.",
        )
        step4_text = t(
            "lan_sharing.guide_step_4",
            default="4. Enter the Local IP and HTTP/SOCKS5 Port shown above and save.",
        )

        guide_card = ft.Container(
            bgcolor="#13141C",
            border_radius=10,
            padding=8,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.INFO_OUTLINED, color="#8B5CF6", size=14),
                            ft.Text(
                                t("lan_sharing.guide_title", default="Quick Connection Guide"),
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color="#8B5CF6",
                                rtl=self.is_rtl,
                            ),
                        ],
                        spacing=4,
                    ),
                    ft.Text(step1_text, size=10, color="#8E8C99", rtl=self.is_rtl),
                    ft.Text(step2_text, size=10, color="#8E8C99", rtl=self.is_rtl),
                    ft.Text(step3_text, size=10, color="#8E8C99", rtl=self.is_rtl),
                    ft.Text(step4_text, size=10, color="#8E8C99", rtl=self.is_rtl),
                ],
                spacing=3,
            ),
        )

        # ── Master Layout ────────────────────────────────────────────────────
        self.content = ft.Column(
            controls=[
                header_row,
                badges_row,
                qr_card,
                guide_card,
            ],
            spacing=6,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def _update_qr_box(self, enabled: bool):
        """Update QR box content dynamically in real-time when switch is toggled."""
        if enabled:
            qr_str = generate_qr_base64(f"http://{self.local_ip}:{self.http_port}")
            if qr_str:
                self._qr_box.bgcolor = "white"
                self._qr_box.content = ft.Image(
                    src=f"data:image/png;base64,{qr_str}",
                    width=170,
                    height=170,
                    fit=ft.BoxFit.CONTAIN,
                )
                return

        # Fallback / Disabled state
        self._qr_box.bgcolor = "#13141C"
        self._qr_box.content = ft.Column(
            [
                ft.Icon(
                    ft.Icons.WIFI_OFF_ROUNDED,
                    size=34,
                    color=ft.Colors.with_opacity(0.35, ft.Colors.WHITE),
                ),
                ft.Text(
                    t("lan_sharing.disabled_placeholder", default="LAN Sharing Disabled"),
                    color="grey",
                    size=10,
                    rtl=self.is_rtl,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        )

    def _copy(self, value: str):
        try:
            page = self.page
            if page:
                page.run_task(page.clipboard.set, value)
                toast_mgr = getattr(page, "_toast_manager", None)
                if toast_mgr:
                    copied_label = t("lan.copied", default="copied!")
                    toast_mgr.show(f"{value} {copied_label}", "success", 2000)
        except Exception:
            pass

    def _on_toggle_change(self, e):
        """Handle LAN switch toggle in real-time without requiring page navigation/refresh."""
        try:
            enabled = e.control.value
            self.allow_lan = enabled

            # 1. Update shared global configuration state
            if self._app_context and hasattr(self._app_context, "settings"):
                self._app_context.settings.set_allow_lan(enabled)

            # 2. Re-detect IP and re-render QR box dynamically
            self.local_ip = get_real_local_ip()
            self._ip_text_ctrl.value = self.local_ip
            self._update_qr_box(enabled)

            # 3. Synchronize sidebar button state in real-time
            if self._on_lan_toggle:
                self._on_lan_toggle(enabled)

            try:
                if self.page:
                    sidebar = getattr(self.page, "_nav_sidebar", None)
                    if not sidebar and hasattr(self.page, "_window"):
                        sidebar = getattr(self.page._window, "_nav_sidebar", None)
                    if sidebar:
                        sidebar.update_lan_button(enabled)
            except Exception:
                pass

            self.update()
        except Exception:
            pass
