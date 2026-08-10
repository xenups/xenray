"""Connection Guide Card Component - 4-step LAN connection instructions."""

from __future__ import annotations

import flet as ft

from src.core.i18n import t


class ConnectionGuideCard(ft.Container):
    """Container listing 4-step LAN connection instructions."""

    def __init__(self, is_rtl: bool = False) -> None:
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

        super().__init__(
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
                                rtl=is_rtl,
                            ),
                        ],
                        spacing=4,
                    ),
                    ft.Text(step1_text, size=10, color="#8E8C99", rtl=is_rtl),
                    ft.Text(step2_text, size=10, color="#8E8C99", rtl=is_rtl),
                    ft.Text(step3_text, size=10, color="#8E8C99", rtl=is_rtl),
                    ft.Text(step4_text, size=10, color="#8E8C99", rtl=is_rtl),
                ],
                spacing=3,
            ),
        )
