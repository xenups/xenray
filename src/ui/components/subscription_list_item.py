"""Subscription list item component."""
from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.i18n import t


class SubscriptionListItem(ft.Container):
    """
    Subscription item with a simple popup menu.
    """

    def __init__(self, sub: dict, on_click: Callable, on_delete: Callable = None):
        super().__init__()
        self.height = 65
        self._sub = sub
        self._on_click = on_click
        self._on_delete = on_delete

        # --- Menu Items ---
        menu_items = [
            ft.PopupMenuItem(
                content=ft.Text(t("server_list.copy_link")),
                icon=ft.Icons.LINK,
                on_click=self._copy_link,
            ),
        ]
        if on_delete:
            menu_items.append(
                ft.PopupMenuItem(
                    content=ft.Text(t("server_list.delete")),
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

        # Custom Row to match ServerListItem metrics
        foreground_content = ft.Row(
            [
                ft.Container(
                    content=ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED, color=ft.Colors.BLUE_400, size=24),
                    padding=ft.padding.only(left=5, right=10),
                ),
                ft.Column(
                    [
                        ft.Text(
                            sub.get("name", "Unknown Subscription"),
                            weight=ft.FontWeight.BOLD,
                            size=14,
                            no_wrap=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            sub.get("url", ""),
                            size=11,
                            color=ft.Colors.GREY_500,
                            no_wrap=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=2,
                    alignment=ft.MainAxisAlignment.CENTER,
                    expand=True,
                ),
                self.menu_button,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        from src.ui.helpers.gradient_helper import GradientHelper

        self.content = foreground_content
        self.bgcolor = "#121212"
        self.gradient = GradientHelper.get_flag_gradient(None)  # Default gradient
        self.border = (
            ft.border.all(1, ft.Colors.OUTLINE_VARIANT)
            if hasattr(ft.Colors, "OUTLINE_VARIANT")
            else ft.border.all(1, ft.Colors.OUTLINE)
        )
        self.border_radius = 8
        self.margin = ft.margin.symmetric(horizontal=10)  # Added to reduce width
        self.padding = ft.padding.symmetric(horizontal=10, vertical=8)
        self.on_click = lambda e: self._on_click(self._sub)

    def _copy_link(self, e):
        try:
            url = self._sub.get("url", "")
            if self.page:
                self.page.set_clipboard(url)
                # Use toast manager if available
                if hasattr(self.page, "_toast_manager"):
                    self.page._toast_manager.success(t("server_list.subscription_link_copied"), 2000)
                self.page.update()
        except Exception:
            # Silently fail if clipboard operation fails
            pass

    def _delete_item(self, e):
        if self._on_delete:
            self._on_delete(self._sub["id"])
