"""ConfigCard component with animated neon sweep border trace for inspection/processing state."""

from __future__ import annotations

import asyncio
import json
from typing import Callable, Optional

import flet as ft

from src.core.i18n import t
from src.core.logger import logger
from src.ui.components.common.neon_sweep_border import NeonSweepBorder
from src.ui.helpers.gradient_helper import GradientHelper
from src.utils.link_parser import LinkParser


class ConfigCard(ft.Container):
    """Card displaying a single configuration item with an animated neon sweep gradient border during inspection."""

    def __init__(
        self,
        profile: dict,
        on_select: Callable[[dict], None],
        on_delete: Optional[Callable[[str], None]] = None,
        is_selected: bool = False,
        read_only: bool = False,
        cached_ping: Optional[tuple] = None,
        is_inspecting: Optional[bool] = None,
    ):
        super().__init__()
        self._profile = profile
        self._on_select = on_select
        self._on_delete = on_delete
        self._read_only = read_only
        self._is_selected = is_selected

        self._is_inspecting = False
        self._inspect_task: Optional[asyncio.Task] = None
        self._pending_start = False

        # Build inner card control with a fully opaque solid background so the
        # sweep gradient only ever shows through the 1.5px border gap.
        self._inner_card = self._build_inner_card(cached_ping)
        self._inner_container = self._inner_card

        # Neon sweep-glow border — the SHARED reusable component (ConfigCard's
        # exact pattern: 1.5px frame + rotating SweepGradient disc + opaque
        # inner mask). The card is larger than the default button size, so pass
        # the card dimensions; the disc starts at the generous construction
        # fallback and is refined to the diagonal by _on_card_size_changed.
        self._neon = NeonSweepBorder(
            child=self._inner_card,
            width=360,
            height=62,
            border_radius=12,
        )

        # Alias the component's disc as _border_container (historic name) so
        # existing callers/tests keep working unchanged.
        self._border_container = self._neon._disc
        self._sweep_gradient = self._neon._sweep_gradient
        self._disc_diameter = self._neon._disc_diameter

        # Outer Border Container (acts as 1.5px border frame around card) —
        # the card IS the border frame (same pattern as the original).
        self.padding = self._neon.padding
        self.border_radius = ft.BorderRadius.all(12)
        self.margin = ft.Margin.symmetric(horizontal=10)
        self.clip_behavior = self._neon.clip_behavior
        self.on_click = lambda e: self._on_select(self._profile)
        self.content = self._neon.content
        self.on_size_change = self._on_card_size_changed

        self._update_border_style()

        # Subscribe to EventBus for inspection start/completion
        # NO per-card EventBus subscriptions: a 1000+ server list would create
        # thousands of subscribers. Inspection events are delegated centrally by
        # the ServerList, which looks up THIS card via its _item_map and calls the
        # public start_inspection_animation / stop_inspection_animation /
        # update_ping methods directly.

        # Check initial inspection status (explicit flag wins over profile hints)
        if is_inspecting is None:
            status = profile.get("status") or profile.get("state")
            is_inspecting = (
                status == "inspecting" or bool(profile.get("is_inspecting")) or bool(profile.get("inspecting"))
            )
        if is_inspecting:
            self.start_inspection_animation()

    def _build_inner_card(self, cached_ping: Optional[tuple]) -> ft.Container:
        # Extract data
        config = self._profile.get("config", {})
        address, port = self._extract_address_port(config)
        name = self._profile.get("name", "Unknown")

        # Determine protocol
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

        # Ping state — uninspected profiles default to a subtle "-" indicator without blocking selection
        last_ping = "-"
        last_ping_color = "#94A3B8"
        if cached_ping:
            cached_text, last_ping_color, cached_val = cached_ping
            if cached_val is not None and cached_val < 999999:
                last_ping = t("connection.latency_ms", value=cached_val)
            else:
                last_ping = cached_text
        elif self._profile.get("last_latency_val") is not None:
            latency_val = self._profile.get("last_latency_val")
            last_ping = t("connection.latency_ms", value=latency_val)
            last_ping_color = self._get_ping_color(latency_val)
        elif self._profile.get("last_latency"):
            import re

            raw_ping = self._profile["last_latency"]
            match = re.search(r"(\d+)", str(raw_ping))
            if match:
                last_ping = t("connection.latency_ms", value=int(match.group(1)))
            else:
                last_ping = raw_ping
            latency_val = self._profile.get("last_latency_val", 999999)
            last_ping_color = self._get_ping_color(latency_val)
        elif self._profile.get("ping") is not None:
            latency_val = self._profile.get("ping")
            if isinstance(latency_val, (int, float)) and latency_val < 999999:
                last_ping = t("connection.latency_ms", value=int(latency_val))
                last_ping_color = self._get_ping_color(latency_val)
            else:
                last_ping = str(latency_val)

        self.latency_text = ft.Text(
            last_ping,
            size=11,
            color=last_ping_color if last_ping not in ("-", "—", "...", "N/A") else "#94A3B8",
            weight=ft.FontWeight.W_400,
        )

        # Ping badge — clicking it re-inspects THIS card through the shared
        # server_inspector/ping_service pipeline (non-blocking + throttled),
        # re-running the neon sweep and updating only this badge on completion.
        self.ping_badge = ft.Container(
            content=self.latency_text,
            on_click=self._on_ping_click,
            tooltip=t("server_list.test_latency", default="Test latency"),
            padding=ft.Padding.symmetric(horizontal=2, vertical=6),
        )

        country_code = self._profile.get("country_code")
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

        menu_items = [
            ft.PopupMenuItem(
                content=t("server_list.share"),
                icon=ft.Icons.SHARE_ROUNDED,
                on_click=self._copy_config,
            ),
        ]
        if not self._read_only and self._on_delete:
            menu_items.append(
                ft.PopupMenuItem(
                    content=t("server_list.delete"),
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

        middle_content = ft.Column(
            [
                ft.Text(
                    name,
                    weight=ft.FontWeight.W_300,
                    size=15,
                    color=ft.Colors.WHITE,
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.Text(
                    f"{protocol} | {address}:{port}",
                    size=11,
                    weight=ft.FontWeight.W_300,
                    color="#94A3B8",
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
            spacing=2,
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )

        row_content = ft.Row(
            [
                ft.Container(content=self.flag_img, padding=ft.Padding.only(left=5)),
                middle_content,
                ft.Column(
                    [self.ping_badge],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=0,
                ),
                self.menu_button,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # The inner card's SOLID #161922 bgcolor is the opaque "donut hole" that
        # masks the outer sweep gradient. The translucent country-flag tint lives
        # in an overlay ON TOP of that solid base (Stack), so the sweep gradient
        # behind this card can never bleed through the card interior.
        self._flag_gradient_overlay = ft.Container(
            expand=True,
            border_radius=ft.BorderRadius.all(10.5),
            gradient=GradientHelper.get_flag_gradient(country_code),
        )

        return ft.Container(
            content=ft.Stack(
                controls=[
                    self._flag_gradient_overlay,
                    ft.Container(
                        content=row_content,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                        expand=True,
                    ),
                ],
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            ),
            height=62,
            bgcolor="#161922",
            border_radius=ft.BorderRadius.all(10.5),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            on_click=lambda e: self._on_select(self._profile) if self._on_select else None,
            ink=True,
        )

    def _update_border_style(self):
        """Update rotating border disc or static border based on inspection and selection state."""
        if self._is_inspecting:
            self.border = None
            self._neon._disc.gradient = self._sweep_gradient
        else:
            self._neon._disc.gradient = None
            if self._is_selected:
                self.border = ft.Border.all(width=1, color=ft.Colors.with_opacity(0.40, "#A855F7"))
            else:
                self.border = ft.Border.all(width=1, color=ft.Colors.with_opacity(0.06, ft.Colors.WHITE))

    def _on_card_size_changed(self, e):
        """Size the rotating border disc to this card's diagonal.

        Flutter interpolates the rotation on the GPU, but a rotating rectangle
        clips its corners out of the thin border ring. Sizing the disc to the
        card's diagonal (>= any rotated point's radius) keeps the neon arc
        tracing every edge without clipping artifacts.
        """
        w = getattr(e, "width", None)
        h = getattr(e, "height", None)
        if not w or not h:
            return
        self._neon.resize_disc(w, h)
        self._disc_diameter = self._neon._disc_diameter

    def start_inspection_animation(self):
        """Start the animated neon sweep gradient border trace loop.

        The disc is constructed with its `rotate=0.0` rotation anchor and the GPU
        ``animate_rotation`` already attached, so it mounts at the origin state
        with the animation engine ready. This coroutine is scheduled immediately
        (or from :meth:`did_mount` if the card is not yet attached) and, after a
        short frame flush, targets the first full turn — so the native 0 -> 2π
        transition begins interpolating on the very next frame instead of Flutter
        drawing the disc directly at the target angle on its first build.
        """
        if self._is_inspecting:
            return
        self._is_inspecting = True
        self._update_border_style()
        self._neon._animating = True
        self._neon._disc.gradient = self._sweep_gradient
        if self._safe_page() is not None:
            self._schedule_animation()
        else:
            self._neon._pending_start = True
            self._pending_start = True

    def stop_inspection_animation(self):
        """Cancel the animation task and restore standard static border styling."""
        self._is_inspecting = False
        self._pending_start = False
        self._neon.stop()
        self._inspect_task = None
        self._update_border_style()
        self._safe_update()

    def did_mount(self):
        """Flet lifecycle hook — start the pending animation once the card is attached.

        Two cases:
        1. Normal: start_inspection_animation() was called while unmounted but
           the inspection is STILL in flight (_is_inspecting=True). Schedule the
           sweep directly.
        2. Race (first ping after app start): the card was built on a background
           thread (page not yet attached -> _pending_start=True) and the
           inspection COMPLETED before the card mounted (_is_inspecting=False).
           Re-enter start_inspection_animation(): the card is now attached, so
           _safe_page() resolves and the sweep actually renders.
        """
        if self._pending_start:
            self._pending_start = False
            if self._is_inspecting:
                # Delegate the mount-race to the component via the card's
                # scheduling shim (it holds the pending flag for the
                # disc-level animation).
                self._neon._pending_start = True
                self._schedule_animation()
            else:
                self.start_inspection_animation()

    def _safe_page(self) -> Optional[ft.Page]:
        """RuntimeError-safe page property getter."""
        try:
            return self.page
        except (RuntimeError, AttributeError):
            return None

    def _schedule_animation(self):
        """Delegate the sweep scheduling to the shared NeonSweepBorder.

        Kept as a thin shim (the pre-refactor card scheduled its own loop
        here) so callers/tests that reach for this internal still work.
        """
        # Route the scheduling through the component (it owns the sweep task
        # and the pending-start flag); the result is mirrored back here.
        result = self._neon._schedule_animation()
        self._inspect_task = self._neon._sweep_task
        self._pending_start = self._neon._pending_start
        return result

    def _safe_update(self):
        """Request a UI update without raising when the control is not attached."""
        try:
            if self._safe_page() is not None:
                self.update()
        except Exception:
            pass

    def _get_ping_color(self, val):
        if val < 1000:
            return ft.Colors.GREEN
        if val < 2000:
            return ft.Colors.ORANGE
        return ft.Colors.RED

    def _copy_config(self, e):
        """Share config link."""
        try:
            link = LinkParser.generate_link(self._profile.get("config", {}), self._profile.get("name", "server"))
            if not link:
                link = json.dumps(self._profile.get("config", {}), indent=2)

            if link and self.page:
                self.page.run_task(self.page.clipboard.set, link)
                if hasattr(self.page, "_toast_manager"):
                    self.page._toast_manager.success(t("server_list.link_copied"), 2000)
        except Exception as ex:
            logger.error(f"[ConfigCard] Share failed for {self._profile.get('name')}: {ex}")

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

    def _on_ping_click(self, e=None):
        """Manually re-inspect THIS card via the shared inspection pipeline.

        Uses the same non-blocking, throttled server_inspector/ping_service flow
        as auto-inspection: the inspecting event starts the native neon sweep,
        and the inspected event stops it and updates ONLY this card's badge.
        """
        from src.services.connection.server_inspector import server_inspector

        try:
            server_inspector.inspect(self._profile)
        except Exception:
            pass

    def update_ping(self, latency_str, color):
        """Update ping with pre-calculated color."""
        self.latency_text.value = latency_str
        self.latency_text.color = color
        self.latency_text.weight = ft.FontWeight.W_400
        try:
            if self.latency_text.page:
                self.latency_text.update()
        except Exception:
            pass

    def update_icon(self, code, name=""):
        if code:
            self.flag_img.content = ft.Image(
                src=f"/flags/{code.lower()}.svg",
                width=28,
                height=28,
                fit=ft.BoxFit.COVER,
                gapless_playback=True,
                filter_quality=ft.FilterQuality.HIGH,
                error_content=ft.Icon(ft.Icons.PUBLIC, size=28, color=ft.Colors.GREY_400),
            )
            self._flag_gradient_overlay.gradient = GradientHelper.get_flag_gradient(code)
        else:
            self.flag_img.content = ft.Icon(ft.Icons.PUBLIC, size=28, color=ft.Colors.GREY_400)
            self._flag_gradient_overlay.gradient = GradientHelper.get_flag_gradient(None)

        # Targeted updates ONLY: re-render the flag icon and the translucent flag
        # tint overlay. The whole-card `update()` is deliberately avoided here so
        # a mid-inspection icon refresh never re-serializes the rotating disc
        # subtree (which would reset the neon animation).
        try:
            if self.flag_img.page:
                self.flag_img.update()
        except Exception:
            pass
        try:
            if self._flag_gradient_overlay.page:
                self._flag_gradient_overlay.update()
        except Exception:
            pass

    def will_unmount(self):
        """Clean up the animation task on unmount (no per-card EventBus subscription)."""
        self.stop_inspection_animation()


ConfigListItem = ConfigCard
