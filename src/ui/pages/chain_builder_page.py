"""Chain builder page for creating/editing outbound chains."""

from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from src.core.app_context import AppContext
from src.core.i18n import t
from src.ui.components.chain import ChainNodeRow
from src.ui.components.common import PageHeader
from src.ui.controllers.chain_builder_controller import ChainBuilderController


class ChainBuilderPage(ft.Container):
    """Full-page view for creating and editing outbound chains."""

    def __init__(
        self,
        app_context: AppContext,
        on_back: Callable,
        on_save: Optional[Callable[[str, List[str]], None]] = None,
        existing_chain: Optional[dict] = None,
    ):
        self._app_context = app_context
        self._on_back = on_back
        self._on_save = on_save
        self._existing_chain = existing_chain

        self._controller = ChainBuilderController(app_context=app_context, existing_chain=existing_chain)
        self._chain_items: List[dict] = []
        self._available_profiles = self._controller.load_available_profiles()

        super().__init__(
            expand=True,
            padding=0,
            bgcolor=ft.Colors.with_opacity(0.3, "#0f172a"),
            blur=ft.Blur(20, 20, ft.BlurTileMode.MIRROR),
        )

        self._setup_ui()

        if existing_chain:
            for profile_id in existing_chain.get("items", []):
                self._add_chain_item(None, profile_id)
        else:
            self._add_chain_item()
            self._add_chain_item()

        self._validate()

    def _setup_ui(self) -> None:
        header = PageHeader(
            title=t("chain.edit_title") if self._existing_chain else t("chain.title"),
            on_back=self._on_back,
        )

        self._name_field = ft.TextField(
            label=t("chain.name_label"),
            hint_text=t("chain.name_hint"),
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
            value=self._existing_chain.get("name", "") if self._existing_chain else "",
            on_change=lambda e: self._validate(),
        )

        self._chain_list = ft.ListView(
            spacing=0,
            expand=True,
            padding=ft.Padding.symmetric(vertical=10),
        )

        self._add_button = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=20, color=ft.Colors.PRIMARY),
                    ft.Text(t("chain.add_item"), size=13, color=ft.Colors.PRIMARY),
                ],
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=20, vertical=12),
            ink=True,
            on_click=self._add_chain_item,
        )

        self._error_text = ft.Text("", color=ft.Colors.ERROR, size=12, visible=False)

        self._save_button = ft.ElevatedButton(
            t("chain.save"),
            icon=ft.Icons.SAVE,
            on_click=self._handle_save,
            disabled=True,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                color=ft.Colors.ON_PRIMARY,
                bgcolor=ft.Colors.PRIMARY,
                padding=ft.Padding.symmetric(horizontal=30, vertical=15),
            ),
        )

        self.content = ft.Column(
            [
                header,
                ft.Container(
                    content=ft.Column(
                        [
                            self._name_field,
                            ft.Container(
                                content=self._chain_list,
                                expand=True,
                                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                                border_radius=8,
                            ),
                            self._add_button,
                            self._error_text,
                            ft.Container(height=10),
                            ft.Row([self._save_button], alignment=ft.MainAxisAlignment.CENTER),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    padding=ft.Padding.all(20),
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        )

    def _create_dropdown(self, selected_id: Optional[str] = None) -> ft.Dropdown:
        options = [ft.dropdown.Option(p["id"], p["name"]) for p in self._available_profiles]

        return ft.Dropdown(
            options=options,
            value=selected_id,
            expand=True,
            text_size=13,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            hint_text=t("chain.select_outbound"),
            border_color=ft.Colors.OUTLINE_VARIANT,
            focused_border_color=ft.Colors.PRIMARY,
            on_select=lambda e: self._validate(),
        )

    def _add_chain_item(self, e=None, profile_id: Optional[str] = None) -> None:
        item_index = len(self._chain_items)
        dropdown = self._create_dropdown(profile_id)
        item_data = {"id": f"item-{item_index}", "dropdown": dropdown}
        self._chain_items.append(item_data)
        self._rebuild_chain_list()
        self._validate()

    def _remove_chain_item(self, item_id: str) -> None:
        self._chain_items = [i for i in self._chain_items if i["id"] != item_id]
        self._rebuild_chain_list()
        self._validate()

    def _rebuild_chain_list(self) -> None:
        self._chain_list.controls.clear()

        for idx, item in enumerate(self._chain_items):
            is_first = idx == 0
            is_last = idx == len(self._chain_items) - 1

            if is_first:
                position_label = t("chain.entry_label")
                position_color = ft.Colors.GREEN
            elif is_last:
                position_label = t("chain.exit_label")
                position_color = ft.Colors.BLUE
            else:
                position_label = f"#{idx + 1}"
                position_color = ft.Colors.ON_SURFACE_VARIANT

            self._chain_list.controls.append(
                ChainNodeRow(
                    position_label=position_label,
                    position_color=position_color,
                    dropdown=item["dropdown"],
                    item_id=item["id"],
                    on_remove=self._remove_chain_item,
                    disabled=len(self._chain_items) <= 2,
                )
            )

        if self._chain_list.page:
            self._chain_list.update()

    def _validate(self) -> bool:
        name = self._name_field.value.strip() if self._name_field.value else ""
        profile_ids = [item["dropdown"].value for item in self._chain_items if item["dropdown"].value]

        is_valid, error_key = self._controller.validate_chain(name, profile_ids)
        if not is_valid:
            self._set_error(t(error_key))
            return False

        self._clear_error()
        return True

    def _set_error(self, message: str) -> None:
        self._error_text.value = f"⚠️ {message}"
        self._error_text.visible = True
        self._save_button.disabled = True
        if self._error_text.page:
            self._error_text.update()
            self._save_button.update()

    def _clear_error(self) -> None:
        self._error_text.visible = False
        self._save_button.disabled = False
        if self._error_text.page:
            self._error_text.update()
            self._save_button.update()

    def _handle_save(self, e) -> None:
        if not self._validate():
            return

        name = self._name_field.value.strip()
        profile_ids = [item["dropdown"].value for item in self._chain_items if item["dropdown"].value]

        saved_chain = self._controller.save_chain(name, profile_ids)
        if self._on_save and saved_chain:
            self._on_save(saved_chain["name"], saved_chain["items"])

        self._on_back(None)
