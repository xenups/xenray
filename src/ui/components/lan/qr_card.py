"""LAN Proxy QR Code card component."""

from __future__ import annotations

from typing import Optional

import flet as ft

from src.core.i18n import t


class QRCard(ft.Container):
    """Container holding 'Scan to Connect' text and the QR image box.

    Owns the internal QR container and exposes high-level reactive methods so
    pages never touch raw Flet container/content state directly.
    """

    def __init__(self, is_rtl: bool = False):
        self._is_rtl = is_rtl

        self._qr_box = ft.Container(
            width=170,
            height=170,
            border_radius=8,
            padding=4,
            bgcolor="#13141C",
            alignment=ft.Alignment.CENTER,
        )
        self._qr_box.content = self._build_placeholder()

        super().__init__(
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
                        rtl=is_rtl,
                    ),
                    self._qr_box,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            ),
        )

    @property
    def is_qr_shown(self) -> bool:
        """Whether a rendered QR image is currently displayed."""
        return isinstance(self._qr_box.content, ft.Image)

    def set_qr_visible(self, visible: bool) -> None:
        """Show or hide the QR image box (loading placeholder while visible)."""
        self._qr_box.bgcolor = "#13141C"
        self._qr_box.content = self._build_loading() if visible else self._build_placeholder()
        self._refresh()

    def show_loading(self) -> None:
        """Render the loading state while a QR code resolves asynchronously."""
        self._qr_box.bgcolor = "#13141C"
        self._qr_box.content = self._build_loading()
        self._refresh()

    def update_qr(self, qr_str: Optional[str]) -> None:
        """Render the QR image from a base64 PNG string, or the disabled placeholder."""
        if qr_str:
            self._qr_box.bgcolor = "white"
            self._qr_box.content = self._build_qr_image(qr_str)
        else:
            self._qr_box.bgcolor = "#13141C"
            self._qr_box.content = self._build_placeholder()
        self._refresh()

    def _build_qr_image(self, qr_str: str) -> ft.Image:
        return ft.Image(
            src=f"data:image/png;base64,{qr_str}",
            width=170,
            height=170,
            fit=ft.BoxFit.CONTAIN,
        )

    def _build_loading(self) -> ft.Column:
        """Skeleton loading state while the QR code generates asynchronously.

        A QR-like skeleton (grid of blocks) with a gentle pulsing opacity —
        reads as "the QR is being generated" rather than a bare spinner.
        The pulse is driven by Flet's native ``animate_opacity`` (GPU) so it
        costs ~zero Python CPU.
        """
        # A stylised QR skeleton: 3 corner finder squares + a few data blocks,
        # plus a small pulsing label underneath.
        block = ft.Container(
            width=12,
            height=12,
            border_radius=2,
            bgcolor=ft.Colors.with_opacity(0.35, ft.Colors.WHITE),
        )

        def finder() -> ft.Container:
            return ft.Container(
                width=30,
                height=30,
                border_radius=3,
                border=ft.Border.all(2, ft.Colors.with_opacity(0.45, ft.Colors.WHITE)),
                padding=6,
                content=ft.Container(
                    bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.WHITE),
                    border_radius=2,
                ),
            )

        # Build a 5x5 skeleton grid: 3 finders at corners + scattered blocks
        grid_cells = []
        for r in range(5):
            row = []
            for c in range(5):
                is_finder = (r in (0, 4) and c in (0, 4)) or (r == 4 and c == 0) or (r == 0 and c == 4)
                is_finder = (r, c) in {(0, 0), (0, 4), (4, 0)}
                if is_finder:
                    row.append(finder())
                elif (r + c) % 2 == 0 and (r, c) not in {(0, 1), (1, 0), (4, 4)}:
                    row.append(block)
                else:
                    row.append(ft.Container(width=12, height=12))
            grid_cells.append(ft.Row(row, spacing=5, tight=True))

        pulse_label = ft.Container(
            content=ft.Text(
                t("lan_sharing.generating_qr", default="Generating..."),
                size=10,
                color=ft.Colors.with_opacity(0.6, ft.Colors.WHITE),
                text_align=ft.TextAlign.CENTER,
                rtl=self._is_rtl,
            ),
            animate_opacity=900,
            opacity=0.5,
        )

        return ft.Column(
            [
                ft.Container(
                    content=ft.Column(grid_cells, spacing=5, tight=True),
                    alignment=ft.Alignment.CENTER,
                    animate_opacity=1100,
                    opacity=0.85,
                ),
                pulse_label,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )

    def _build_placeholder(self) -> ft.Column:
        return ft.Column(
            [
                ft.Icon(
                    ft.Icons.WIFI_OFF_ROUNDED,
                    size=34,
                    color=ft.Colors.with_opacity(0.35, ft.Colors.WHITE),
                ),
                ft.Text(
                    t(
                        "lan_sharing.disabled_placeholder",
                        default="LAN Sharing Disabled",
                    ),
                    color="grey",
                    size=10,
                    rtl=self._is_rtl,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        )

    def _refresh(self) -> None:
        """Push QR box mutations to the page without a full page re-render."""
        try:
            if self._qr_box.page:
                self._qr_box.update()
        except Exception:
            pass
