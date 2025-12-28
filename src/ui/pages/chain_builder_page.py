"""Chain builder page for creating/editing outbound chains."""
from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from src.core.app_context import AppContext
from src.core.i18n import t


class ChainBuilderPage(ft.Container):
    """
    Full-page view for creating and editing outbound chains.

    Features:
    - Dropdown selection for each chain item (base profiles only)
    - Visual arrows showing flow direction
    - Remove button per item
    - Inline validation feedback
    """

    def __init__(
        self,
        app_context: AppContext,
        on_back: Callable,
        on_save: Optional[Callable[[str, List[str]], None]] = None,
        existing_chain: Optional[dict] = None,
    ):
        """
        Initialize the chain builder page.

        Args:
            app_context: AppContext instance
            on_back: Callback when back button is clicked
            on_save: Callback when chain is saved (name, profile_ids)
            existing_chain: Optional existing chain for editing
        """
        self._app_context = app_context
        self._on_back = on_back
        self._on_save = on_save
        self._existing_chain = existing_chain

        # State
        self._chain_items: List[dict] = []  # [{id: str, dropdown: ft.Dropdown}]

        # Build available profiles (base profiles only, no chains)
        self._available_profiles = self._load_available_profiles()

        super().__init__(
            expand=True,
            padding=0,
            bgcolor=ft.Colors.with_opacity(0.3, "#0f172a"),
            blur=ft.Blur(20, 20, ft.BlurTileMode.MIRROR),
        )

        self._setup_ui()

        # Initialize with existing chain items or empty
        if existing_chain:
            for profile_id in existing_chain.get("items", []):
                self._add_chain_item(None, profile_id)
        else:
            # Start with 2 empty slots
            self._add_chain_item()
            self._add_chain_item()

        self._validate()

    def _load_available_profiles(self) -> List[dict]:
        """Load all base profiles (excluding chains) for dropdown options."""
        profiles = []

        # Add local profiles
        for profile in self._app_context.profiles.load_all():
            profiles.append(
                {
                    "id": profile.get("id"),
                    "name": profile.get("name", "Unknown"),
                    "source": "local",
                }
            )

        # Add subscription profiles
        for sub in self._app_context.subscriptions.load_all():
            for profile in sub.get("profiles", []):
                profiles.append(
                    {
                        "id": profile.get("id"),
                        "name": f"{profile.get('name', 'Unknown')} ({sub.get('name', '')})",
                        "source": "subscription",
                    }
                )

        return profiles

    def _setup_ui(self):
        """Build the page UI."""
        # Header with back button - simplified, no subtitle
        header = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(ft.Icons.ARROW_BACK, on_click=self._on_back),
                    ft.Text(
                        t("chain.edit_title") if self._existing_chain else t("chain.title"),
                        size=20,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                spacing=10,
            ),
            padding=ft.padding.symmetric(horizontal=10, vertical=10),
            bgcolor=ft.Colors.with_opacity(0.2, "#1e293b"),
            blur=ft.Blur(10, 10, ft.BlurTileMode.MIRROR),
        )

        # Name input
        self._name_field = ft.TextField(
            label=t("chain.name_label"),
            hint_text=t("chain.name_hint"),
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
            value=self._existing_chain.get("name", "") if self._existing_chain else "",
            on_change=lambda e: self._validate(),
        )

        # Chain list container - scrollable
        self._chain_list = ft.ListView(
            spacing=0,
            expand=True,
            padding=ft.padding.symmetric(vertical=10),
        )

        # Add button
        self._add_button = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=20, color=ft.Colors.PRIMARY),
                    ft.Text(t("chain.add_item"), size=13, color=ft.Colors.PRIMARY),
                ],
                spacing=8,
            ),
            padding=ft.padding.symmetric(horizontal=20, vertical=12),
            ink=True,
            on_click=self._add_chain_item,
        )

        # Error display
        self._error_text = ft.Text(
            "",
            color=ft.Colors.ERROR,
            size=12,
            visible=False,
        )

        # Save button
        self._save_button = ft.ElevatedButton(
            t("chain.save"),
            icon=ft.Icons.SAVE,
            on_click=self._handle_save,
            disabled=True,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                color=ft.Colors.ON_PRIMARY,
                bgcolor=ft.Colors.PRIMARY,
                padding=ft.padding.symmetric(horizontal=30, vertical=15),
            ),
        )

        # Assemble the page - scrollable content
        self.content = ft.Column(
            [
                header,
                ft.Container(
                    content=ft.Column(
                        [
                            # Name input
                            self._name_field,
                            # Chain list (scrollable)
                            ft.Container(
                                content=self._chain_list,
                                expand=True,
                                border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
                                border_radius=8,
                            ),
                            # Add button
                            self._add_button,
                            # Error
                            self._error_text,
                            ft.Container(height=10),
                            # Save button
                            ft.Row(
                                [self._save_button],
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    padding=ft.padding.all(20),
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        )

    def _create_dropdown(self, selected_id: Optional[str] = None) -> ft.Dropdown:
        """Create a dropdown for profile selection."""
        options = [ft.dropdown.Option(p["id"], p["name"]) for p in self._available_profiles]

        return ft.Dropdown(
            options=options,
            value=selected_id,
            expand=True,
            text_size=13,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            hint_text=t("chain.select_outbound"),
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
            on_change=lambda e: self._validate(),
        )

    def _add_chain_item(self, e=None, profile_id: Optional[str] = None):
        """Add a new chain item slot."""
        item_index = len(self._chain_items)
        dropdown = self._create_dropdown(profile_id)

        item_data = {
            "id": f"item-{item_index}",
            "dropdown": dropdown,
        }
        self._chain_items.append(item_data)

        self._rebuild_chain_list()
        self._validate()

    def _remove_chain_item(self, item_id: str):
        """Remove a chain item."""
        self._chain_items = [i for i in self._chain_items if i["id"] != item_id]
        self._rebuild_chain_list()
        self._validate()

    def _rebuild_chain_list(self):
        """Rebuild the visual chain list."""
        self._chain_list.controls.clear()

        for idx, item in enumerate(self._chain_items):
            is_first = idx == 0
            is_last = idx == len(self._chain_items) - 1

            # Label for position
            if is_first:
                position_label = t("chain.entry_label")
                position_color = ft.Colors.GREEN
            elif is_last:
                position_label = t("chain.exit_label")
                position_color = ft.Colors.BLUE
            else:
                position_label = f"#{idx + 1}"
                position_color = ft.Colors.ON_SURFACE_VARIANT

            # Row with index, dropdown, and remove button
            row = ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(
                                position_label,
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=position_color,
                            ),
                            width=60,
                        ),
                        item["dropdown"],
                        ft.IconButton(
                            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                            icon_size=20,
                            icon_color=ft.Colors.ERROR,
                            tooltip=t("chain.remove_item"),
                            on_click=lambda e, item_id=item["id"]: self._remove_chain_item(item_id),
                            disabled=len(self._chain_items) <= 2,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                padding=ft.padding.symmetric(horizontal=20, vertical=6),
            )

            self._chain_list.controls.append(row)

            # Add arrow between items (except after last)
            # if not is_last:
            #     self._chain_list.controls.append(
            #         ft.Container(
            #             content=ft.Row(
            #                 [
            #                     ft.Container(width=85),
            #                     ft.Icon(
            #                         ft.Icons.ARROW_DOWNWARD,
            #                         size=18,
            #                         color=ft.Colors.ON_SURFACE_VARIANT,
            #                     ),
            #                 ],
            #             ),
            #             padding=ft.padding.symmetric(vertical=2),
            #         )
            #     )

        if self._chain_list.page:
            self._chain_list.update()

    def _validate(self) -> bool:
        """Validate the current chain configuration."""
        # Check name
        name = self._name_field.value.strip() if self._name_field.value else ""
        if not name:
            self._set_error(t("add_dialog.required"))
            return False

        # Collect selected profile IDs
        profile_ids = []
        for item in self._chain_items:
            value = item["dropdown"].value
            if value:
                profile_ids.append(value)

        # Check minimum items
        if len(profile_ids) < 2:
            self._set_error(t("chain.validation.min_items"))
            return False

        # Use AppContext validation
        is_valid, error = self._app_context.validate_chain(profile_ids)
        if not is_valid:
            self._set_error(error)
            return False

        self._clear_error()
        return True

    def _set_error(self, message: str):
        """Display an error message."""
        self._error_text.value = f"⚠️ {message}"
        self._error_text.visible = True
        self._save_button.disabled = True
        if self._error_text.page:
            self._error_text.update()
            self._save_button.update()

    def _clear_error(self):
        """Clear the error message."""
        self._error_text.visible = False
        self._save_button.disabled = False
        if self._error_text.page:
            self._error_text.update()
            self._save_button.update()

    def _handle_save(self, e):
        """Handle save button click."""
        if not self._validate():
            return

        name = self._name_field.value.strip()
        profile_ids = [item["dropdown"].value for item in self._chain_items if item["dropdown"].value]

        # Save the chain
        if self._existing_chain:
            self._app_context.update_chain(
                self._existing_chain["id"],
                {"name": name, "items": profile_ids},
            )
        else:
            self._app_context.save_chain(name, profile_ids)

        # Call save callback if provided
        if self._on_save:
            self._on_save(name, profile_ids)

        # Navigate back
        self._on_back(None)
