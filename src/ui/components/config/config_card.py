"""ConfigCard component with animated neon sweep border trace for inspection/processing state."""

from __future__ import annotations

import asyncio
import math
import json
from typing import Callable, Optional

import flet as ft

from src.core.i18n import t
from src.core.logger import logger
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

        # Neon Sweep Gradient for Inspection State — a narrow glowing arc that
        # fades quickly to transparent so it reads as a thin border trace rather
        # than a pie/cone fill across the card.
        self._sweep_gradient = ft.SweepGradient(
            center=ft.Alignment.CENTER,
            colors=["#A3A8FE", "#00F2FE", "#00000000", "#00000000"],
            stops=[0.0, 0.10, 0.22, 1.0],
            rotation=0.0,
        )

        # Build inner card control with a fully opaque solid background so the
        # sweep gradient only ever shows through the 1.5px border gap.
        self._inner_card = self._build_inner_card(cached_ping)
        self._inner_container = self._inner_card

        # Rotating border disc — a large circular layer that carries the neon
        # sweep. It is POSITIONED (left/top) so it never contributes to the
        # Stack's size, and it is clipped to this card via clip_behavior. Only
        # this layer rotates (GPU-accelerated by Flutter); the content card (a
        # sibling) stays fixed.
        #
        # The diameter is PRE-CALCULATED at construction (generous fallback so
        # the arc can trace every edge from frame 0 without waiting for the
        # async on_size_change layout callback, which only refines it later).
        #
        # IMPORTANT: the disc stays permanently MOUNTED (never toggled via
        # visible). Appearance is controlled solely by `gradient` (None while
        # idle). It is constructed with the `rotate=0.0` rotation ANCHOR and the
        # GPU `animate_rotation` already attached, so it enters the DOM at the
        # origin state with the animation engine ready — Flutter can begin
        # interpolating the first target change immediately instead of waiting a
        # full frame-pass to set up the AnimatedRotation.
        self._disc_diameter = 800.0
        self._border_container = ft.Container(
            width=self._disc_diameter,
            height=self._disc_diameter,
            border_radius=self._disc_diameter / 2,
            left=(360 - self._disc_diameter) / 2,
            top=(62 - self._disc_diameter) / 2,
            gradient=None,
            rotate=ft.Rotate(angle=0.0),
            animate_rotation=ft.Animation(
                duration=1500,
                curve=ft.AnimationCurve.LINEAR,
            ),
        )

        # Outer Border Container (acts as 1.5px border frame around card)
        self.padding = ft.Padding.all(1.5)
        self.border_radius = ft.BorderRadius.all(12)
        self.margin = ft.Margin.symmetric(horizontal=10)
        self.clip_behavior = ft.ClipBehavior.HARD_EDGE
        self.on_click = lambda e: self._on_select(self._profile)
        self.content = ft.Stack(
            controls=[self._border_container, self._inner_card],
            alignment=ft.Alignment.CENTER,
            clip_behavior=ft.ClipBehavior.NONE,
        )
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

        # Ping state
        last_ping = "..."
        last_ping_color = ft.Colors.GREY_500
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

        self.latency_text = ft.Text(
            last_ping,
            size=11,
            color=last_ping_color if last_ping != "..." else ft.Colors.GREY_500,
            weight=ft.FontWeight.BOLD if last_ping != "..." else ft.FontWeight.NORMAL,
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
        )

    def _update_border_style(self):
        """Update rotating border disc or static border based on inspection and selection state."""
        if self._is_inspecting:
            self.border = None
            self._border_container.gradient = self._sweep_gradient
        else:
            self._border_container.gradient = None
            if self._is_selected:
                self.border = ft.Border.all(width=2, color=ft.Colors.BLUE)
            else:
                self.border = ft.Border.all(width=1, color=ft.Colors.OUTLINE)

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
        w, h = float(w), float(h)
        diameter = math.hypot(w, h)
        self._disc_diameter = diameter
        self._border_container.width = diameter
        self._border_container.height = diameter
        self._border_container.border_radius = diameter / 2
        self._border_container.left = (w - diameter) / 2
        self._border_container.top = (h - diameter) / 2
        try:
            self._border_container.update()
        except Exception:
            pass

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
        if self._safe_page() is not None:
            self._schedule_animation()
        else:
            self._pending_start = True

    def stop_inspection_animation(self):
        """Cancel the animation task and restore standard static border styling."""
        self._is_inspecting = False
        self._pending_start = False
        if self._inspect_task and not self._inspect_task.done():
            self._inspect_task.cancel()
        self._inspect_task = None
        self._border_container.rotate = ft.Rotate(angle=0.0)
        self._update_border_style()
        self._safe_update()

    def _schedule_animation(self):
        """Schedule the sweep animation coroutine on an available event loop."""
        page = self._safe_page()
        if page is not None:
            if self._inspect_task is None or self._inspect_task.done():
                self._pending_start = False
                self._inspect_task = page.run_task(self._animate_sweep)
            return

        try:
            loop = asyncio.get_running_loop()
            if self._inspect_task is None or self._inspect_task.done():
                self._pending_start = False
                self._inspect_task = loop.create_task(self._animate_sweep())
        except RuntimeError:
            # No running event loop (card built on a background thread, not yet
            # mounted). did_mount() schedules the loop once attached to a page.
            pass

    def did_mount(self):
        """Flet lifecycle hook — start the pending animation once the card is attached."""
        if self._is_inspecting and self._pending_start:
            self._schedule_animation()

    async def _animate_sweep(self):
        """Drive the native hardware-accelerated rotation of the border disc.

        The disc mounts at its `rotate=0.0` anchor with ``animate_rotation``
        already attached. This coroutine yields for a short frame flush so that
        anchor is actually rendered by Flutter, then targets the first full turn
        (2π) in a SEPARATE frame — making the native 0 -> 2π transition
        interpolate immediately instead of Flutter drawing the control directly
        at the target angle on its first animated frame.

        Afterwards the loop nudges the target forward by a full turn (2π) each
        cycle — one tiny ``rotate`` patch per 1.5s, interpolated at 60 FPS on the
        GPU.
        """
        try:
            # Frame flush: let the 0.0 anchor render before applying the first
            # target, so the target below lands on a distinct client frame.
            await asyncio.sleep(0.05)
            if not self._is_inspecting:
                return
            full_turns = 0
            while self._is_inspecting:
                full_turns += 1
                self._border_container.rotate = ft.Rotate(angle=2 * math.pi * full_turns)
                try:
                    self._border_container.update()
                except Exception:
                    pass
                await asyncio.sleep(1.4)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[ConfigCard] Animation exception: {e}")
        finally:
            self._border_container.rotate = ft.Rotate(angle=0.0)
            if not self._is_inspecting:
                self._update_border_style()
            self._safe_update()

    def _safe_page(self) -> Optional[ft.Page]:
        """RuntimeError-safe page property getter."""
        try:
            return self.page
        except (RuntimeError, AttributeError):
            return None

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
        from src.services.server_inspector import server_inspector

        try:
            server_inspector.inspect(self._profile)
        except Exception:
            pass

    def update_ping(self, latency_str, color):
        """Update ping with pre-calculated color."""
        self.latency_text.value = latency_str
        self.latency_text.color = color
        self.latency_text.weight = ft.FontWeight.BOLD
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
