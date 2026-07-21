"""Routing rules management page with i18n support."""
import flet as ft

from src.core.app_context import AppContext
from src.core.i18n import t


class RoutingPage(ft.Container):
    def __init__(self, app_context: AppContext, on_back):
        self._app_context = app_context
        self._on_back = on_back
        self._rules = self._app_context.routing.load_rules()
        self._toggles = self._app_context.routing.load_toggles()
        self._current_tab = "quick"

        super().__init__(
            expand=True,
            padding=0,
            bgcolor=ft.Colors.with_opacity(0.3, "#0f172a"),
            blur=ft.Blur(20, 20, ft.BlurTileMode.MIRROR),
        )
        self._setup_ui()

    def _create_toggle_row(self, key: str, title: str, subtitle: str, icon) -> ft.Container:
        """Create a toggle row for quick settings."""
        switch = ft.Switch(
            value=self._toggles.get(key, False),
            on_change=lambda e, k=key: self._on_toggle_change(k, e.control.value),
        )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=20, color=ft.Colors.PRIMARY),
                    ft.Column(
                        [
                            ft.Text(title, size=13, weight=ft.FontWeight.W_500),
                            ft.Text(subtitle, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    switch,
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=15, vertical=12),
            border=ft.Border.only(bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )

    def _on_toggle_change(self, key: str, value: bool):
        """Handle toggle change."""
        self._toggles[key] = value
        self._app_context.routing.save_toggle(key, value)

    def _setup_ui(self):
        # Header
        header = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(ft.Icons.ARROW_BACK, on_click=self._on_back),
                    ft.Column(
                        [
                            ft.Text(t("routing.title"), size=20, weight=ft.FontWeight.BOLD),
                            ft.Text(
                                t("routing.subtitle"),
                                size=12,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                    ),
                ],
                spacing=10,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=10),
            bgcolor=ft.Colors.with_opacity(0.2, "#1e293b"),
            blur=ft.Blur(10, 10, ft.BlurTileMode.MIRROR),
        )

        # Quick Settings Content (shown when Quick tab is selected)
        self._quick_settings_view = ft.Container(
            content=ft.Column(
                [
                    self._create_toggle_row(
                        "block_udp_443",
                        t("routing.block_udp443"),
                        t("routing.block_udp443_desc"),
                        ft.Icons.BLOCK,
                    ),
                    self._create_toggle_row(
                        "block_ads",
                        t("routing.block_ads"),
                        t("routing.block_ads_desc"),
                        ft.Icons.AD_UNITS_OUTLINED,
                    ),
                    self._create_toggle_row(
                        "direct_private_ips",
                        t("routing.direct_private"),
                        t("routing.direct_private_desc"),
                        ft.Icons.LAN,
                    ),
                    self._create_toggle_row(
                        "direct_local_domains",
                        t("routing.direct_local"),
                        t("routing.direct_local_desc"),
                        ft.Icons.HOME_WORK,
                    ),
                ],
                spacing=0,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=10),
            expand=True,
        )

        # Build per-tab content for rule management tabs
        tab_keys = ["direct", "proxy", "block"]
        self._rule_tabs = {}
        tab_contents: list[ft.Control] = [self._quick_settings_view]

        for tab_key in tab_keys:
            input_field = ft.TextField(
                label=t("routing.domain_or_ip"),
                hint_text=t("routing.hint"),
                expand=True,
                text_size=14,
                height=40,
                content_padding=10,
                border_radius=8,
            )
            input_field.on_submit = lambda e, k=tab_key, inp=input_field: self._add_rule(k, inp)
            add_btn = ft.ElevatedButton(
                t("routing.add"),
                icon=ft.Icons.ADD,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    color=ft.Colors.ON_PRIMARY,
                    bgcolor=ft.Colors.PRIMARY,
                    padding=ft.Padding.symmetric(horizontal=20),
                ),
                on_click=lambda e, k=tab_key, inp=input_field: self._add_rule(k, inp),
                height=40,
            )
            list_view = ft.ListView(
                expand=True,
                spacing=2,
                padding=ft.Padding.symmetric(horizontal=20, vertical=0),
            )

            self._rule_tabs[tab_key] = {
                "input": input_field,
                "list_view": list_view,
            }

            tab_contents.append(
                ft.Column(
                    [
                        ft.Container(
                            content=ft.Row([input_field, add_btn], spacing=10),
                            padding=ft.Padding.symmetric(horizontal=20, vertical=10),
                        ),
                        ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT, opacity=0.5),
                        list_view,
                    ],
                    spacing=0,
                    expand=True,
                )
            )

        # Tabs
        self._tabs = ft.Tabs(
            length=4,
            selected_index=0,
            animation_duration=300,
            on_change=self._on_tab_change,
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label=t("routing.quick_settings"), icon=ft.Icons.TUNE),
                            ft.Tab(label=t("routing.direct"), icon=ft.Icons.DIRECTIONS),
                            ft.Tab(label=t("routing.proxy"), icon=ft.Icons.VPN_LOCK),
                            ft.Tab(label=t("routing.block"), icon=ft.Icons.BLOCK),
                        ],
                        divider_color=ft.Colors.TRANSPARENT,
                        indicator_color=ft.Colors.PRIMARY,
                        label_color=ft.Colors.PRIMARY,
                        unselected_label_color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.TabBarView(
                        expand=True,
                        controls=tab_contents,
                    ),
                ],
            ),
        )

        # Main Layout
        self.content = ft.Column(
            [header, self._tabs],
            spacing=0,
        )

    def _on_tab_change(self, e):
        idx = self._tabs.selected_index
        tab_map = {0: "quick", 1: "direct", 2: "proxy", 3: "block"}
        self._current_tab = tab_map.get(idx, "quick")
        if idx > 0:
            self._refresh_list(self._current_tab, update=True)

    def _refresh_list(self, tab_key, update=True):
        list_view = self._rule_tabs[tab_key]["list_view"]
        list_view.controls.clear()
        items = self._rules.get(tab_key, [])

        if not items:
            tab_name = t(f"routing.{tab_key}")
            list_view.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(
                                ft.Icons.LIST_ALT,
                                size=48,
                                color=ft.Colors.OUTLINE_VARIANT,
                            ),
                            ft.Text(
                                t("routing.no_rules", type=tab_name),
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=50,
                    opacity=0.5,
                )
            )

        for item in items:
            list_view.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(item, size=14, weight=ft.FontWeight.W_500, expand=True),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                icon_size=20,
                                icon_color=ft.Colors.RED_400,
                                tooltip=t("routing.remove"),
                                on_click=lambda e, i=item: self._delete_rule(i),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                    border=ft.Border.only(bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
                )
            )

        if update and self.page:
            list_view.update()

    def _add_rule(self, tab_key, input_field):
        val = input_field.value.strip()
        if not val:
            return

        if val not in self._rules[tab_key]:
            self._rules[tab_key].append(val)
            self._save()
            self._refresh_list(tab_key, update=True)

        input_field.value = ""
        input_field.focus()
        input_field.update()

    def _delete_rule(self, item):
        if item in self._rules[self._current_tab]:
            self._rules[self._current_tab].remove(item)
            self._save()
            self._refresh_list(self._current_tab, update=True)

    def _save(self):
        self._app_context.routing.save_rules(self._rules)
