"""Server list header component with i18n support."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import t


class ServerListHeader(ft.Container):
    """Header component for the server list with dynamic main/subscription modes."""

    def __init__(
        self,
        get_sort_mode: Callable[[], str],
        set_sort_mode: Callable[[str], None],
        on_test_latency: Callable,
        on_add_click: Callable,
        on_back_click: Optional[Callable] = None,
        on_update_subscription: Optional[Callable] = None,
        on_delete_subscription: Optional[Callable] = None,
        on_cancel_ping: Optional[Callable] = None,
    ):
        self._get_sort_mode = get_sort_mode
        self._set_sort_mode = set_sort_mode
        self._on_test_latency = on_test_latency
        self._on_add_click = on_add_click
        self._on_back_click = on_back_click
        self._on_update_subscription = on_update_subscription
        self._on_delete_subscription = on_delete_subscription
        self._on_cancel_ping = on_cancel_ping

        self._current_subscription: Optional[dict] = None
        self._ping_active = False
        self._ping_all_btn: Optional[ft.IconButton] = None
        self._inner_row = ft.Row([], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        super().__init__(content=self._inner_row, padding=ft.Padding.only(left=15, right=5))
        self.show_main_header()

    def _create_ping_btn(self) -> ft.IconButton:
        """Create the Ping All button; toggles to 'Stop Ping' while active."""
        self._ping_all_btn = ft.IconButton(
            ft.Icons.SPEED,
            tooltip=t("server_list.test_latency"),
            on_click=self._on_ping_click,
        )
        return self._ping_all_btn

    def _on_ping_click(self, e=None):
        if self._ping_active:
            if self._on_cancel_ping:
                self._on_cancel_ping()
        else:
            self._on_test_latency()

    def set_ping_state(self, active: bool) -> None:
        """Toggle the Ping All button between 'Ping All' and 'Stop Ping' (in-place)."""
        self._ping_active = active
        if self._ping_all_btn is None:
            return
        self._ping_all_btn.icon = ft.Icons.STOP_ROUNDED if active else ft.Icons.SPEED
        self._ping_all_btn.tooltip = (
            t("server_list.stop_ping", default="Stop Ping") if active else t("server_list.test_latency")
        )
        try:
            self._ping_all_btn.update()
        except Exception:
            pass

    def _create_sort_menu(self) -> ft.PopupMenuButton:
        """Creates the sort popup menu."""
        current_sort = self._get_sort_mode()

        def set_sort(mode: str):
            self._set_sort_mode(mode)
            if self._current_subscription:
                self.show_subscription_header(self._current_subscription)
            else:
                self.show_main_header()

        return ft.PopupMenuButton(
            icon=ft.Icons.SORT,
            tooltip=t("server_list.sort"),
            items=[
                ft.PopupMenuItem(
                    content=t("server_list.sort_name"),
                    checked=current_sort == "name_asc",
                    on_click=lambda e: set_sort("name_asc"),
                ),
                ft.PopupMenuItem(
                    content=t("server_list.sort_latency"),
                    checked=current_sort == "ping_asc",
                    on_click=lambda e: set_sort("ping_asc"),
                ),
            ],
        )

    def show_main_header(self):
        """Display the main server list header."""
        self._current_subscription = None
        self._inner_row.controls = [
            ft.Text(
                t("server_list.title"),
                size=22,
                weight=ft.FontWeight.W_300,
                color=ft.Colors.WHITE,
                style=ft.TextStyle(letter_spacing=0.8),
            ),
            ft.Row(
                [
                    self._create_ping_btn(),
                    self._create_sort_menu(),
                ]
            ),
        ]
        self._safe_update()

    def show_subscription_header(self, sub: dict):
        """Display header for a subscription view."""
        self._current_subscription = sub
        sub_id = sub.get("id")

        self._inner_row.controls = [
            ft.Row(
                [
                    ft.IconButton(
                        ft.Icons.ARROW_BACK,
                        on_click=lambda e: (self._on_back_click() if self._on_back_click else None),
                    ),
                    ft.Text(sub["name"], size=17, weight=ft.FontWeight.BOLD),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                [
                    self._create_ping_btn(),
                    self._create_sort_menu(),
                    ft.PopupMenuButton(
                        icon=ft.Icons.MORE_VERT,
                        items=[
                            ft.PopupMenuItem(
                                content=t("server_list.update_subscription"),
                                icon=ft.Icons.REFRESH,
                                on_click=lambda e: (
                                    self._on_update_subscription(sub_id) if self._on_update_subscription else None
                                ),
                            ),
                            ft.PopupMenuItem(
                                content=t("server_list.delete_subscription"),
                                icon=ft.Icons.DELETE,
                                on_click=lambda e: (
                                    self._on_delete_subscription(sub_id) if self._on_delete_subscription else None
                                ),
                            ),
                        ],
                    ),
                ]
            ),
        ]
        self._safe_update()

    def _safe_update(self):
        """Safely update the component if mounted."""
        try:
            if self.page:
                self.update()
        except Exception:
            pass
