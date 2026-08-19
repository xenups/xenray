"""Connection Guide Card Component - 4-step LAN connection instructions."""

from __future__ import annotations

import flet as ft

from src.core.i18n import t


class ConnectionGuideCard(ft.Container):
    """Container listing 4-step LAN connection instructions in a minimal, compact glass card."""

    def __init__(self, is_rtl: bool = False) -> None:
        step1_text = t(
            "lan_sharing.guide_step_1",
            default="1. Connect target device (Phone, TV, PC) to the same Wi-Fi network.",
        )
        step2_text = t(
            "lan_sharing.guide_step_2",
            default="2. Set Proxy to Manual mode in the Wi-Fi or app settings on the device.",
        )
        step3_text = t(
            "lan_sharing.guide_step_3",
            default="3. Enter the Local IP and HTTP/SOCKS5 Port shown above.",
        )
        step4_text = t(
            "lan_sharing.guide_step_4",
            default="4. Save and start browsing through your proxy connection.",
        )

        super().__init__(
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.WHITE),
            border_radius=10,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.04, ft.Colors.WHITE)),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.HELP_OUTLINE_ROUNDED, color="#94A3B8", size=12),
                            ft.Text(
                                t("lan_sharing.guide_title", default="Quick Guide"),
                                size=10.5,
                                weight=ft.FontWeight.W_400,
                                color="#94A3B8",
                                rtl=is_rtl,
                            ),
                        ],
                        spacing=4,
                    ),
                    ft.Text(
                        step1_text,
                        size=9.5,
                        weight=ft.FontWeight.W_300,
                        color="rgba(255, 255, 255, 0.45)",
                        rtl=is_rtl,
                    ),
                    ft.Text(
                        step2_text,
                        size=9.5,
                        weight=ft.FontWeight.W_300,
                        color="rgba(255, 255, 255, 0.45)",
                        rtl=is_rtl,
                    ),
                    ft.Text(
                        step3_text,
                        size=9.5,
                        weight=ft.FontWeight.W_300,
                        color="rgba(255, 255, 255, 0.45)",
                        rtl=is_rtl,
                    ),
                    ft.Text(
                        step4_text,
                        size=9.5,
                        weight=ft.FontWeight.W_300,
                        color="rgba(255, 255, 255, 0.45)",
                        rtl=is_rtl,
                    ),
                ],
                spacing=1.5,
            ),
        )
