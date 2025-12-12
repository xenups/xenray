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
    ):
        self._get_sort_mode = get_sort_mode
        self._set_sort_mode = set_sort_mode
        self._on_test_latency = on_test_latency
        self._on_add_click = on_add_click
        self._on_back_click = on_back_click
        self._on_update_subscription = on_update_subscription
        self._on_delete_subscription = on_delete_subscription

        self._current_subscription: Optional[dict] = None
        self._inner_row = ft.Row([], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        super().__init__(content=self._inner_row, padding=0)
        self.show_main_header()

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
                    text=t("server_list.sort_name"),
                    checked=current_sort == "name_asc",
                    on_click=lambda e: set_sort("name_asc"),
                ),
                ft.PopupMenuItem(
                    text=t("server_list.sort_latency"),
                    checked=current_sort == "ping_asc",
                    on_click=lambda e: set_sort("ping_asc"),
                ),
            ],
        )

    def show_main_header(self):
        """Display the main server list header."""
        self._current_subscription = None
        self._inner_row.controls = [
            ft.Text(t("server_list.title"), size=20, weight=ft.FontWeight.BOLD),
            ft.Row(
                [
                    ft.IconButton(
                        ft.Icons.SPEED,
                        tooltip=t("server_list.test_latency"),
                        on_click=lambda e: self._on_test_latency(),
                    ),
                    self._create_sort_menu(),
                    ft.IconButton(
                        ft.Icons.ADD,
                        tooltip=t("server_list.add_server"),
                        on_click=self._on_add_click,
                    ),
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
                        on_click=lambda e: self._on_back_click()
                        if self._on_back_click
                        else None,
                    ),
                    ft.Text(sub["name"], size=20, weight=ft.FontWeight.BOLD),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                [
                    ft.IconButton(
                        ft.Icons.SPEED,
                        tooltip=t("server_list.test_latency"),
                        on_click=lambda e: self._on_test_latency(),
                    ),
                    self._create_sort_menu(),
                    ft.PopupMenuButton(
                        icon=ft.Icons.MORE_VERT,
                        items=[
                            ft.PopupMenuItem(
                                text=t("server_list.update_subscription"),
                                icon=ft.Icons.REFRESH,
                                on_click=lambda e: self._on_update_subscription(sub_id)
                                if self._on_update_subscription
                                else None,
                            ),
                            ft.PopupMenuItem(
                                text=t("server_list.delete_subscription"),
                                icon=ft.Icons.DELETE,
                                on_click=lambda e: self._on_delete_subscription(sub_id)
                                if self._on_delete_subscription
                                else None,
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
