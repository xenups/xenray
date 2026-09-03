"""Node Card Component - Current node stats, server icon, location metadata, and change server action."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.country_translator import translate_country
from src.core.i18n import t
from src.ui.theme import AppColors, create_glass_container


class NodeCardComponent:
    """Bento container showing current node details, location, protocol, server icon, and Change Server button."""

    def __init__(self, on_change_server_click: Callable):
        self._on_change_server_click = on_change_server_click

        PURPLE = AppColors.PRIMARY
        WHITE = ft.Colors.WHITE
        MUTED_WHITE = AppColors.ON_SURFACE_VARIANT

        self._server_icon_container = ft.Container(
            content=ft.Icon(ft.Icons.DNS_ROUNDED, size=18, color=WHITE),
            width=32,
            height=32,
            border_radius=16,
            bgcolor=ft.Colors.with_opacity(0.25, PURPLE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.4, PURPLE)),
            alignment=ft.Alignment.CENTER,
        )

        self._server_name_text = ft.Text(
            t("server_list.no_server", default="No Server Selected"),
            size=14,
            weight=ft.FontWeight.W_800,
            color=WHITE,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self._server_latency_badge = ft.Container(
            content=ft.Text("--", size=10, weight=ft.FontWeight.W_700, color=WHITE),
            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.2, PURPLE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, PURPLE)),
        )

        self._row_flag_img = ft.Image(src="", width=18, height=12, border_radius=2, visible=False)
        self._row_country_text = ft.Text("--", size=11, color=WHITE, weight=ft.FontWeight.W_600)
        self._country_value_row = ft.Row(
            [self._row_flag_img, self._row_country_text],
            spacing=6,
            alignment=ft.MainAxisAlignment.END,
        )

        self._server_protocol_text = ft.Text("--", size=11, color=WHITE, weight=ft.FontWeight.W_600)
        self._encryption_text = ft.Text("--", size=11, color=WHITE, weight=ft.FontWeight.W_600)
        self._server_ip_text = ft.Text("--", size=11, color=WHITE, weight=ft.FontWeight.W_600)

        self._change_server_btn = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.SYNC_ALT, size=14, color=WHITE),
                    ft.Text(
                        t("dashboard.change_server", default="Change Server"),
                        size=11,
                        weight=ft.FontWeight.W_700,
                        color=WHITE,
                    ),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_click=self._on_change_server_click,
            ink=True,
            border_radius=20,
            padding=ft.Padding.symmetric(vertical=8, horizontal=14),
            bgcolor=ft.Colors.with_opacity(0.08, WHITE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.2, WHITE)),
        )

        def detail_row(label, value_control):
            return ft.Row(
                [
                    ft.Text(label, size=11, color=MUTED_WHITE, weight=ft.FontWeight.W_500),
                    value_control,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        content = ft.Column(
            [
                ft.Text(
                    t("dashboard.current_node", default="CURRENT NODE"),
                    size=10,
                    weight=ft.FontWeight.W_700,
                    color=MUTED_WHITE,
                ),
                ft.Row(
                    [
                        self._server_icon_container,
                        ft.Column(
                            [
                                self._server_name_text,
                                ft.Row([self._server_latency_badge]),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(height=1, color=ft.Colors.with_opacity(0.12, WHITE)),
                ft.Column(
                    [
                        detail_row(
                            t("dashboard.country", default="Country"),
                            self._country_value_row,
                        ),
                        detail_row(
                            t("dashboard.protocol", default="Protocol"),
                            self._server_protocol_text,
                        ),
                        detail_row(
                            t("dashboard.encryption", default="Encryption"),
                            self._encryption_text,
                        ),
                        detail_row(
                            t("dashboard.server_ip", default="Server IP"),
                            self._server_ip_text,
                        ),
                    ],
                    spacing=4,
                ),
                self._change_server_btn,
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self.view = create_glass_container(
            content=content,
            expand=4,
            padding=14,
        )

    def update_server_info(
        self,
        name: str = "",
        latency: str = "",
        protocol: str = "",
        encryption: str = "",
        server_ip: str = "",
        country_code: str = "",
        country_name: str = "",
        local_ip: str | None = None,
        **kwargs,
    ):
        """Update Current Node bento card stats and server metadata matching design screenshot."""
        self._server_name_text.value = name
        self._server_latency_badge.content.value = latency
        self._server_protocol_text.value = protocol
        self._encryption_text.value = encryption
        self._server_ip_text.value = server_ip

        loc_text = translate_country(country_code, fallback=country_name) if country_code or country_name else "--"
        self._row_country_text.value = loc_text

        if country_code:
            code_lower = country_code.lower()
            flag_url = f"https://flagcdn.com/w40/{code_lower}.png"
            self._row_flag_img.src = flag_url
            self._row_flag_img.visible = True
        else:
            self._row_flag_img.visible = False

        try:
            if self.view.page:
                self.view.update()
        except Exception:
            pass
