import flet as ft

from src.core.flag_colors import FLAG_COLORS
from src.core.i18n import t


class ServerCard(ft.Container):
    """Server card with Apple glass-like theme and country-based gradient colors."""

    def __init__(self, on_click):
        self._on_click = on_click
        self._current_colors = FLAG_COLORS["default"]

        # Icon Container (Holds Flag or Globe)
        self._globe_icon = ft.Icon(
            ft.Icons.PUBLIC, size=20, color=ft.Colors.ON_SURFACE_VARIANT
        )
        self._icon_container = ft.Container(
            content=self._globe_icon,
            width=36,
            height=36,
            alignment=ft.alignment.center,
            border_radius=18,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
        )

        self._name_text = ft.Text(
            t("server_list.no_server"),
            color=ft.Colors.ON_SURFACE_VARIANT,
            size=15,
            weight=ft.FontWeight.W_600,
        )
        self._address_text = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT)

        # List icon button
        self._list_btn = ft.Container(
            content=ft.Icon(
                ft.Icons.EXPAND_MORE, size=22, color=ft.Colors.ON_SURFACE_VARIANT
            ),
            width=36,
            height=36,
            alignment=ft.alignment.center,
            border_radius=18,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
            on_click=on_click,
        )

        # Main content row
        self._content_row = ft.Row(
            [
                self._icon_container,
                ft.Column(
                    [
                        ft.Text(
                            t("server_list.current_server"),
                            size=10,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            weight=ft.FontWeight.W_400,
                        ),
                        self._name_text,
                        self._address_text,
                    ],
                    expand=True,
                    spacing=2,
                ),
                self._list_btn,
            ]
        )

        # Initialize with glass-like gradient
        super().__init__(
            content=self._content_row,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=[
                    ft.Colors.with_opacity(0.15, "#6366f1"),
                    ft.Colors.with_opacity(0.10, "#8b5cf6"),
                    ft.Colors.with_opacity(0.08, "#6366f1"),
                ],
                tile_mode=ft.GradientTileMode.CLAMP,
            ),
            border=ft.border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE)),
            border_radius=20,
            padding=ft.padding.symmetric(horizontal=16, vertical=14),
            margin=ft.margin.only(left=20, right=20, bottom=16),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=20,
                color=ft.Colors.with_opacity(0.1, ft.Colors.BLACK),
                offset=ft.Offset(0, 4),
            ),
            on_click=on_click,
            animate=ft.Animation(300, ft.AnimationCurve.EASE_OUT),
        )

    def _get_country_colors(self, country_code: str) -> tuple:
        """Get gradient colors for a country."""
        cc = country_code.lower() if country_code else "default"
        return FLAG_COLORS.get(cc, FLAG_COLORS["default"])

    def _update_gradient_colors(self):
        """Update gradient with current country colors."""
        color1, color2 = self._current_colors
        self.gradient = ft.LinearGradient(
            begin=ft.alignment.top_left,
            end=ft.alignment.bottom_right,
            colors=[
                ft.Colors.with_opacity(0.20, color1),
                ft.Colors.with_opacity(0.12, color2),
                ft.Colors.with_opacity(0.08, color1),
            ],
            tile_mode=ft.GradientTileMode.CLAMP,
        )

    def update_server(self, profile):
        """Update server card with profile data."""
        if not profile:
            self._icon_container.content = self._globe_icon
            self._name_text.value = t("server_list.no_server")
            self._name_text.color = ft.Colors.ON_SURFACE_VARIANT
            self._address_text.value = ""
            self._current_colors = FLAG_COLORS["default"]
            self._update_gradient_colors()
        else:
            # Update flag
            cc = profile.get("country_code")
            if cc:
                new_image = ft.Image(
                    src=f"/flags/{cc.lower()}.svg",
                    width=36,
                    height=36,
                    fit=ft.ImageFit.COVER,
                    gapless_playback=True,
                    filter_quality=ft.FilterQuality.HIGH,
                    border_radius=ft.border_radius.all(18),
                    anti_alias=True,
                )
                self._icon_container.content = new_image
                self._icon_container.tooltip = profile.get("country_name", cc)
                self._current_colors = self._get_country_colors(cc)
            else:
                self._icon_container.content = self._globe_icon
                self._current_colors = FLAG_COLORS["default"]

            self._name_text.value = profile["name"]
            self._name_text.color = ft.Colors.ON_SURFACE

            # Address
            try:
                vnext = profile["config"]["outbounds"][0]["settings"]["vnext"][0]
                address = vnext["address"]
                port = vnext["port"]
                self._address_text.value = f"{address}:{port}"
            except Exception:
                self._address_text.value = ""

            self._update_gradient_colors()

        try:
            self._icon_container.update()
            self.update()
        except Exception:
            pass

    def update_theme(self, is_dark: bool):
        """Update card appearance based on theme."""
        if is_dark:
            self.border = ft.border.all(
                1, ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE)
            )
            self._globe_icon.color = ft.Colors.ON_SURFACE_VARIANT
            self._list_btn.bgcolor = ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
            self.shadow.color = ft.Colors.with_opacity(0.15, ft.Colors.BLACK)
        else:
            self.border = ft.border.all(
                1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
            )
            self._globe_icon.color = ft.Colors.ON_SURFACE_VARIANT
            self._list_btn.bgcolor = ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)
            self.shadow.color = ft.Colors.with_opacity(0.08, ft.Colors.BLACK)

        self._update_gradient_colors()
        self.update()
