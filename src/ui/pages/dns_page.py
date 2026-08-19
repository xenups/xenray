"""DNS management page with i18n support."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.app_context import AppContext
from src.core.i18n import t
from src.ui.components.common import PageHeader
from src.ui.components.dns import DNSServerRow
from src.ui.controllers.dns_controller import DNSController
from src.ui.theme import GlassTokens


class DNSPage(ft.Container):
    """DNS management page displaying DNS server entries, priority controls, and addition form."""

    def __init__(self, app_context: AppContext, on_back: Callable):
        self._app_context = app_context
        self._on_back = on_back
        self._controller = DNSController(app_context=app_context)

        super().__init__(
            expand=True,
            padding=0,
            bgcolor=GlassTokens.BG_PAGE,
        )
        self._setup_ui()

    def _setup_ui(self) -> None:
        header = PageHeader(
            title=t("dns.title"),
            subtitle=t("dns.subtitle"),
            on_back=self._on_back,
        )

        self._protocol_dd = ft.Dropdown(
            options=[
                ft.dropdown.Option("udp", "UDP"),
                ft.dropdown.Option("tcp", "TCP"),
                ft.dropdown.Option("doh", "DoH"),
                ft.dropdown.Option("dot", "DoT"),
                ft.dropdown.Option("doq", "DoQ (QUIC)"),
            ],
            value="udp",
            width=120,
            text_size=12,
            content_padding=10,
            border_radius=8,
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
        )

        self._address_input = ft.TextField(
            label=t("dns.address"),
            hint_text=t("dns.hint"),
            expand=True,
            text_size=14,
            height=40,
            content_padding=10,
            border_radius=8,
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
            on_submit=self._add_server,
        )

        add_btn = ft.ElevatedButton(
            t("dns.add"),
            icon=ft.Icons.ADD,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                color=ft.Colors.ON_PRIMARY,
                bgcolor=ft.Colors.PRIMARY,
                padding=ft.Padding.symmetric(horizontal=20),
            ),
            on_click=self._add_server,
            height=40,
        )

        input_container = ft.Container(
            content=ft.Row([self._protocol_dd, self._address_input, add_btn], spacing=10),
            padding=ft.Padding.symmetric(horizontal=20, vertical=10),
        )

        list_header = ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        t("dns.proto"),
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        width=50,
                    ),
                    ft.Text(
                        t("dns.address_header"),
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        expand=True,
                    ),
                    ft.Text(
                        t("dns.actions"),
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        width=80,
                        text_align=ft.TextAlign.RIGHT,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            padding=ft.Padding.symmetric(horizontal=20, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
            border=ft.Border.only(bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )

        self._list_view = ft.ListView(expand=True, spacing=0, padding=0)

        self.content = ft.Column(
            [header, input_container, list_header, self._list_view],
            spacing=0,
        )

        self._refresh_list(update=False)

    def _refresh_list(self, update: bool = True) -> None:
        self._list_view.controls.clear()

        if not self._controller.dns_list:
            self._list_view.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(
                                ft.Icons.DNS_OUTLINED,
                                size=48,
                                color=ft.Colors.OUTLINE_VARIANT,
                            ),
                            ft.Text(t("dns.no_dns"), color=ft.Colors.ON_SURFACE_VARIANT),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=50,
                    opacity=0.5,
                )
            )

        for idx, item in enumerate(self._controller.dns_list):
            self._list_view.controls.append(
                DNSServerRow(idx=idx, item=item, on_move_up=self._move_up, on_delete=self._delete)
            )

        if update and self.page:
            self._list_view.update()

    def _focus_input(self) -> None:
        """Request focus on the address field (focus() is a coroutine in Flet 0.86.1)."""
        try:
            if self._address_input.page is not None:
                self._address_input.page.run_task(self._address_input.focus)
            else:
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._address_input.focus())
                except RuntimeError:
                    pass
        except Exception:
            pass

    def _add_server(self, e) -> None:
        addr = self._address_input.value.strip()
        if not self._controller.add_server(addr, self._protocol_dd.value):
            self._address_input.value = ""
            self._focus_input()
            self._address_input.update()
            return

        # In-place append (no full list rebuild): remove the empty-state
        # placeholder first, then add the single new row.
        if self._list_view.controls and not isinstance(self._list_view.controls[0], DNSServerRow):
            self._list_view.controls.clear()
        new_idx = len(self._controller.dns_list) - 1
        self._list_view.controls.append(
            DNSServerRow(
                idx=new_idx,
                item=self._controller.dns_list[new_idx],
                on_move_up=self._move_up,
                on_delete=self._delete,
            )
        )
        try:
            if self._list_view.page:
                self._list_view.update()
        except Exception:
            pass

        self._address_input.value = ""
        self._focus_input()
        self._address_input.update()

    def _delete(self, idx: int) -> None:
        if self._controller.delete_server(idx):
            self._refresh_list()

    def _move_up(self, idx: int) -> None:
        if self._controller.move_up(idx):
            self._refresh_list()
