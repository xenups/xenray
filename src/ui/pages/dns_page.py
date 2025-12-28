"""DNS management page with i18n support."""
import flet as ft

from src.core.app_context import AppContext
from src.core.i18n import t


class DNSPage(ft.Container):
    def __init__(self, app_context: AppContext, on_back):
        self._app_context = app_context
        self._on_back = on_back
        self._dns_list = self._app_context.dns.load()

        super().__init__(
            expand=True,
            padding=0,
            bgcolor=ft.Colors.with_opacity(0.3, "#0f172a"),
            blur=ft.Blur(20, 20, ft.BlurTileMode.MIRROR),
        )
        self._setup_ui()

    def _setup_ui(self):
        # Header
        header = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(ft.Icons.ARROW_BACK, on_click=self._on_back),
                    ft.Column(
                        [
                            ft.Text(t("dns.title"), size=20, weight=ft.FontWeight.BOLD),
                            ft.Text(
                                t("dns.subtitle"),
                                size=12,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                    ),
                ],
                spacing=10,
            ),
            padding=ft.padding.symmetric(horizontal=10, vertical=10),
            bgcolor=ft.Colors.with_opacity(0.2, "#1e293b"),
            blur=ft.Blur(10, 10, ft.BlurTileMode.MIRROR),
        )

        # Input Area
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
                padding=ft.padding.symmetric(horizontal=20),
            ),
            on_click=self._add_server,
            height=40,
        )

        input_container = ft.Container(
            content=ft.Row([self._protocol_dd, self._address_input, add_btn], spacing=10),
            padding=ft.padding.symmetric(horizontal=20, vertical=10),
        )

        # List Header
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
            padding=ft.padding.symmetric(horizontal=20, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
            border=ft.border.only(bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )

        # List
        self._list_view = ft.ListView(expand=True, spacing=0, padding=0)

        self.content = ft.Column(
            [
                header,
                input_container,
                list_header,
                self._list_view,
            ],
            spacing=0,
        )

        self._refresh_list(update=False)

    def _refresh_list(self, update=True):
        self._list_view.controls.clear()

        if not self._dns_list:
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
                    alignment=ft.alignment.center,
                    padding=50,
                    opacity=0.5,
                )
            )

        for idx, item in enumerate(self._dns_list):
            proto = item.get("protocol", "udp").upper()
            addr = item.get("address", "?")

            row = ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(
                                proto,
                                size=10,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.ON_SURFACE
                                if proto in ["UDP", "TCP"]
                                else ft.Colors.ON_PRIMARY_CONTAINER,
                            ),
                            bgcolor=ft.Colors.BLUE_200 if proto in ["UDP", "TCP"] else ft.Colors.GREEN_200,
                            padding=ft.padding.symmetric(horizontal=6, vertical=2),
                            border_radius=4,
                            width=50,
                            alignment=ft.alignment.center,
                        ),
                        ft.Text(
                            addr,
                            size=13,
                            weight=ft.FontWeight.W_500,
                            expand=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            color=ft.Colors.ON_SURFACE,
                        ),
                        ft.Row(
                            [
                                ft.IconButton(
                                    ft.Icons.ARROW_UPWARD,
                                    icon_size=18,
                                    tooltip=t("dns.move_up"),
                                    on_click=lambda e, i=idx: self._move_up(i),
                                ),
                                ft.IconButton(
                                    ft.Icons.DELETE_OUTLINE,
                                    icon_size=18,
                                    icon_color=ft.Colors.RED_400,
                                    tooltip=t("dns.remove"),
                                    on_click=lambda e, i=idx: self._delete(i),
                                ),
                            ],
                            spacing=0,
                            alignment=ft.MainAxisAlignment.END,
                            width=80,
                        ),
                    ]
                ),
                padding=ft.padding.symmetric(horizontal=20, vertical=12),
                border=ft.border.only(bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
                bgcolor=ft.Colors.with_opacity(0.15, "#1e293b"),
            )
            self._list_view.controls.append(row)

        if update and self.page:
            self._list_view.update()

    def _add_server(self, e):
        addr = self._address_input.value.strip()
        if not addr:
            return

        entry = {"address": addr, "protocol": self._protocol_dd.value, "domains": []}

        self._dns_list.append(entry)
        self._save()
        self._refresh_list()

        self._address_input.value = ""
        self._address_input.focus()
        self._address_input.update()

    def _delete(self, idx):
        if 0 <= idx < len(self._dns_list):
            self._dns_list.pop(idx)
            self._save()
            self._refresh_list()

    def _move_up(self, idx):
        if idx > 0:
            self._dns_list[idx], self._dns_list[idx - 1] = (
                self._dns_list[idx - 1],
                self._dns_list[idx],
            )
            self._save()
            self._refresh_list()

    def _save(self):
        self._app_context.dns.save(self._dns_list)
