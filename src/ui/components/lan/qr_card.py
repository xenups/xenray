"""LAN Proxy QR Code card component."""

from __future__ import annotations

import asyncio
from typing import Optional

import flet as ft

from src.core.i18n import t


class QRCard(ft.Container):
    """Container holding 'Scan with Mobile / TV' text and the QR image box."""

    def __init__(self, is_rtl: bool = False):
        self._is_rtl = is_rtl
        self._pulse_task: Optional[asyncio.Task] = None  # type: ignore[name-defined]
        self._pulsing = False

        self._qr_box = ft.Container(
            width=140,
            height=140,
            border_radius=16,
            padding=10,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
            alignment=ft.Alignment.CENTER,
        )
        self._qr_box.content = self._build_placeholder()

        super().__init__(
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.WHITE),
            border_radius=14,
            padding=ft.Padding.symmetric(vertical=8, horizontal=10),
            alignment=ft.Alignment.CENTER,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.05, ft.Colors.WHITE)),
            content=ft.Column(
                [
                    ft.Text(
                        t("lan_sharing.scan_to_connect", default="Scan with Mobile / TV"),
                        size=11,
                        weight=ft.FontWeight.W_300,
                        color="#94A3B8",
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
        self._stop_pulse()
        self._qr_box.bgcolor = ft.Colors.with_opacity(0.03, ft.Colors.WHITE)
        self._qr_box.border = ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE))
        self._qr_box.shadow = None
        self._qr_box.content = self._build_loading() if visible else self._build_placeholder()
        self._refresh()

    def show_loading(self) -> None:
        """Render the loading state while a QR code resolves asynchronously."""
        self._qr_box.bgcolor = ft.Colors.with_opacity(0.03, ft.Colors.WHITE)
        self._qr_box.border = ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE))
        self._qr_box.shadow = None
        self._qr_box.content = self._build_loading()
        self._start_pulse()
        self._refresh()

    def update_qr(self, qr_str: Optional[str]) -> None:
        """Render the QR image from a base64 PNG string, or the disabled placeholder."""
        self._stop_pulse()
        if qr_str:
            self._qr_box.bgcolor = "white"
            self._qr_box.border = None
            self._qr_box.shadow = ft.BoxShadow(
                spread_radius=2,
                blur_radius=20,
                color="rgba(168, 85, 247, 0.22)",
                offset=ft.Offset(0, 0),
            )
            self._qr_box.content = self._build_qr_image(qr_str)
        else:
            self._qr_box.bgcolor = ft.Colors.with_opacity(0.03, ft.Colors.WHITE)
            self._qr_box.border = ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE))
            self._qr_box.shadow = None
            self._qr_box.content = self._build_placeholder()
        self._refresh()

    def _build_qr_image(self, qr_str: str) -> ft.Image:
        return ft.Image(
            src=f"data:image/png;base64,{qr_str}",
            width=120,
            height=120,
            fit=ft.BoxFit.CONTAIN,
            animate_opacity=450,
            opacity=1.0,
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

    # ------------------------------------------------------------------
    # Loading pulse animation (opacity 0.4 <-> 1.0 on the skeleton)
    # ------------------------------------------------------------------

    def _start_pulse(self) -> None:
        """Start the gentle opacity pulse on the skeleton grid."""
        if self._pulsing:
            return
        self._pulsing = True
        skeleton = self._qr_box.content
        # Seed the loop target from wherever the skeleton currently sits.
        if skeleton is not None and hasattr(skeleton, "controls") and skeleton.controls:
            top = skeleton.controls[0]
            top.opacity = 0.4
        try:
            page = self.page
        except RuntimeError:
            page = None
        if page is not None:
            self._pulse_task = page.run_task(self._pulse_loop)
        else:
            # No live page (headless tests) — animate via the running loop if any.
            try:
                loop = asyncio.get_running_loop()
                self._pulse_task = loop.create_task(self._pulse_loop())
            except RuntimeError:
                pass

    def _stop_pulse(self) -> None:
        """Cancel the pulse loop and restore full opacity."""
        self._pulsing = False
        if self._pulse_task is not None:
            try:
                self._pulse_task.cancel()
            except Exception:
                pass
        self._pulse_task = None
        skeleton = self._qr_box.content
        if skeleton is not None and hasattr(skeleton, "controls") and skeleton.controls:
            try:
                skeleton.controls[0].opacity = 1.0
            except Exception:
                pass

    async def _pulse_loop(self) -> None:
        """Drive opacity 0.4 -> 1.0 -> 0.4 on the skeleton grid top container.

        Each step is a tiny patch interpolated by Flutter's native
        animate_opacity (900ms EASE_IN_OUT), so the pulse is GPU-smooth and
        costs ~zero Python CPU.
        """
        try:
            while self._pulsing:
                skeleton = self._qr_box.content
                if skeleton is not None and hasattr(skeleton, "controls") and skeleton.controls:
                    top = skeleton.controls[0]
                    # Fade down
                    top.opacity = 0.4
                    try:
                        top.update()
                    except Exception:
                        pass
                    await asyncio.sleep(0.9)
                    if not self._pulsing:
                        break
                    # Fade up
                    top.opacity = 1.0
                    try:
                        top.update()
                    except Exception:
                        pass
                    await asyncio.sleep(0.9)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
