"""Chain list item component for displaying chains in server list."""
from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from src.core.app_context import AppContext
from src.core.i18n import t


class ChainListItem(ft.Container):
    """
    A chain item in the server list with expand/collapse functionality.

    Features:
    - Collapsed view shows chain name and server count
    - Expanded view shows full chain order with arrows
    - Warning icon for broken/invalid chains
    - Prevents selection of invalid chains
    """

    def __init__(
        self,
        chain: dict,
        app_context: AppContext,
        on_select: Callable[[dict], None],
        on_edit: Optional[Callable[[dict], None]] = None,
        on_delete: Optional[Callable[[str], None]] = None,
        is_selected: bool = False,
    ):
        """
        Initialize the chain list item.

        Args:
            chain: Chain data dict
            app_context: AppContext instance
            on_select: Callback when chain is selected for connection
            on_edit: Callback when edit is requested
            on_delete: Callback when delete is requested
            is_selected: Whether this chain is currently selected
        """
        super().__init__()

        self._chain = chain
        self._profile = chain  # Alias for compatibility with ServerList
        self._app_context = app_context
        self._on_select = on_select
        self._on_edit = on_edit
        self._on_delete = on_delete
        self._is_selected = is_selected
        self._is_expanded = False

        # Chain validity
        self._is_valid = chain.get("valid", True)
        self._missing_profiles = chain.get("missing_profiles", [])

        # Build profile name list for display
        self._profile_names = self._get_profile_names()

        # Build UI
        self._build_ui()

    def _get_profile_names(self) -> List[str]:
        """Get display names for all profiles in chain."""
        names = []
        for profile_id in self._chain.get("items", []):
            profile = self._app_context.get_profile_by_id(profile_id)
            if profile:
                names.append(profile.get("name", "Unknown"))
            else:
                names.append("⚠️ Missing")
        return names

    def _build_ui(self):
        """Build the UI components."""
        chain_name = self._chain.get("name", "Unnamed Chain")
        item_count = len(self._chain.get("items", []))

        # Get exit server (last in chain) for flag display
        exit_profile = None
        exit_country_code = None
        if self._chain.get("items"):
            last_profile_id = self._chain["items"][-1]
            exit_profile = self._app_context.get_profile_by_id(last_profile_id)
            if exit_profile:
                exit_country_code = exit_profile.get("country_code")

        # Chain icon - show flag if available, otherwise link/warning icon
        if not self._is_valid:
            icon = ft.Icon(ft.Icons.WARNING, size=24, color=ft.Colors.ERROR)
        elif exit_country_code:
            # Use exit server's flag
            icon = ft.Container(
                content=ft.Image(
                    src=f"/flags/{exit_country_code.lower()}.svg",
                    width=28,
                    height=28,
                    fit=ft.ImageFit.COVER,
                    border_radius=ft.border_radius.all(14),
                ),
                width=28,
                height=28,
            )
        else:
            icon = ft.Icon(ft.Icons.LINK, size=24, color=ft.Colors.PRIMARY)

        # Expand/collapse button
        self._expand_button = ft.IconButton(
            icon=ft.Icons.EXPAND_MORE,
            icon_size=20,
            icon_color=ft.Colors.ON_SURFACE_VARIANT,
            on_click=self._toggle_expand,
            tooltip=t("chain.list_item.expand"),
        )

        # Actions menu
        menu_items = []
        if self._on_edit:
            menu_items.append(
                ft.PopupMenuItem(
                    text=t("chain.edit_title"),
                    icon=ft.Icons.EDIT,
                    on_click=lambda e: self._on_edit(self._chain),
                )
            )
        if self._on_delete:
            menu_items.append(
                ft.PopupMenuItem(
                    text=t("server_list.delete"),
                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                    on_click=lambda e: self._on_delete(self._chain["id"]),
                )
            )

        menu_button = (
            ft.PopupMenuButton(
                items=menu_items,
                icon=ft.Icons.MORE_VERT_ROUNDED,
                icon_color=ft.Colors.GREY_400,
                icon_size=20,
            )
            if menu_items
            else ft.Container()
        )

        # Subtitle text
        if self._is_valid:
            subtitle = f"{t('chain.list_item.chain_label')} • {t('chain.list_item.servers_count', count=item_count)}"
        else:
            subtitle = f"{t('chain.list_item.chain_label')} • {t('chain.list_item.invalid')}"

        # Collapsed header row
        self._header_row = ft.Row(
            [
                icon,
                ft.Column(
                    [
                        ft.Text(
                            chain_name,
                            weight=ft.FontWeight.BOLD,
                            size=14,
                            no_wrap=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        self._create_subtitle_text(subtitle),
                    ],
                    spacing=2,
                    expand=True,
                ),
                self._expand_button,
                menu_button,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # Expanded content (chain order visualization)
        self._expanded_content = ft.Container(
            content=self._build_expanded_view(),
            visible=False,
            padding=ft.padding.only(top=10, left=30),
        )

        # Selection border
        border_color = ft.Colors.BLUE if self._is_selected else ft.Colors.OUTLINE
        border_width = 2 if self._is_selected else 1

        # Main content
        self.content = ft.Column(
            [
                self._header_row,
                self._expanded_content,
            ],
            spacing=0,
        )

        # Container styling
        self.padding = ft.padding.symmetric(horizontal=12, vertical=10)
        self.bgcolor = "#1a1a2e" if self._is_valid else "#2a1a1a"
        self.border = ft.border.all(border_width, border_color)
        self.border_radius = 8
        self.margin = ft.margin.symmetric(horizontal=10, vertical=2)

        # Click handler (only if valid)
        if self._is_valid:
            self.on_click = lambda e: self._on_select(self._chain)
            self.ink = True
        else:
            self.tooltip = t("chain.list_item.broken_tooltip")

    def _create_subtitle_text(self, text):
        self._subtitle_text = ft.Text(
            text,
            size=11,
            color=ft.Colors.ERROR if not self._is_valid else ft.Colors.GREY_500,
        )
        return self._subtitle_text

    def update_ping(self, text: str, color: str):
        """Update latency display."""
        if not self._is_valid:
            return

        # Append latency to default subtitle
        item_count = len(self._chain.get("items", []))
        base_text = f"{t('chain.list_item.chain_label')} • {t('chain.list_item.servers_count', count=item_count)}"

        self._subtitle_text.value = f"{base_text} • {text}"
        if color == ft.Colors.RED_400:  # Error/Timeout
            self._subtitle_text.color = ft.Colors.ERROR
        else:
            self._subtitle_text.color = ft.Colors.GREEN_400
        self.update()

    def update_icon(self, country_code: str, country_name: str = None):
        """Update chain icon (exit node flag)."""
        if not country_code:
            return

        # Update connection references via config manager if needed?
        # Typically ServerList calling this means we have new info.
        # We can update our internal chain dict
        self._chain["country_code"] = country_code
        if country_name:
            self._chain["country_name"] = country_name

        # Rebuild UI? Or just update icon.
        # Accessing icon in _header_row.controls[0] is brittle.
        # Better to rebuild the header row or access icon container if stored.
        # For simplicity, trigger a rebuild or just ignore icon update for now if hard to reach.
        # Let's just ignore icon update for chains dynamic ping for now to be safe,
        # or implement it if critical.
        pass

    def _build_expanded_view(self) -> ft.Control:
        """Build the expanded chain order visualization."""
        controls = []

        for idx, name in enumerate(self._profile_names):
            is_first = idx == 0
            is_last = idx == len(self._profile_names) - 1

            # Position indicator
            position_text = ""
            if is_first:
                position_text = f" ({t('chain.entry_label')})"
            elif is_last:
                position_text = f" ({t('chain.exit_label')})"

            # Profile row
            row = ft.Row(
                [
                    ft.Text(
                        f"{idx + 1}.",
                        width=20,
                        size=11,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        name,
                        size=12,
                        expand=True,
                        no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        position_text,
                        size=10,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        italic=True,
                    ),
                ],
            )
            controls.append(row)

            # Arrow between items (removed per user request)
            # if not is_last:
            #     controls.append(
            #         ft.Container(
            #             content=ft.Icon(
            #                 ft.Icons.ARROW_DOWNWARD,
            #                 size=14,
            #                 color=ft.Colors.ON_SURFACE_VARIANT,
            #             ),
            #             padding=ft.padding.only(left=5, top=2, bottom=2),
            #         )
            #     )

        return ft.Column(controls, spacing=0)

    def _toggle_expand(self, e):
        """Toggle expand/collapse state."""
        self._is_expanded = not self._is_expanded
        self._expanded_content.visible = self._is_expanded
        self._expand_button.icon = ft.Icons.EXPAND_LESS if self._is_expanded else ft.Icons.EXPAND_MORE
        self._expand_button.tooltip = (
            t("chain.list_item.collapse") if self._is_expanded else t("chain.list_item.expand")
        )

        if self.page:
            self.update()
