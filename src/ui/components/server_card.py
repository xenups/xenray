import flet as ft

from src.core.flag_colors import FLAG_COLORS
from src.core.i18n import t


class ServerCard(ft.Container):
    """Server card with Apple glass-like theme and country-based gradient colors."""

    def __init__(self, app_context, on_click):
        self._app_context = app_context
        self._on_click = on_click
        self._current_colors = FLAG_COLORS["default"]

        # Icon Container (Holds Flag or Globe)
        self._globe_icon = ft.Icon(ft.Icons.PUBLIC, size=28, color=ft.Colors.ON_SURFACE_VARIANT)
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
            overflow=ft.TextOverflow.ELLIPSIS,
            max_lines=1,
        )
        self._address_text = ft.Text(
            "",
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
            overflow=ft.TextOverflow.ELLIPSIS,
            max_lines=1,
        )

        # List icon button
        self._list_btn = ft.Container(
            content=ft.Icon(ft.Icons.EXPAND_MORE, size=22, color=ft.Colors.ON_SURFACE_VARIANT),
            width=36,
            height=36,
            alignment=ft.alignment.center,
            border_radius=18,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
            on_click=on_click,
        )

        # Country/City text (replaces "Current Server" label)
        self._country_city_text = ft.Text(
            "",
            size=10,
            color=ft.Colors.ON_SURFACE_VARIANT,
            weight=ft.FontWeight.W_400,
            overflow=ft.TextOverflow.ELLIPSIS,
            max_lines=1,
        )

        # Main content row
        self._content_row = ft.Row(
            [
                self._icon_container,
                ft.Column(
                    [
                        self._country_city_text,
                        self._name_text,
                        self._address_text,
                    ],
                    expand=True,
                    spacing=2,
                ),
                self._list_btn,
            ]
        )

        # Initialize with solid gradient + subtle overlay
        super().__init__(
            content=self._content_row,
            bgcolor="#121212",  # Solid background to prevent transparency issues
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=[
                    ft.Colors.with_opacity(0.35, "#6366f1"),
                    ft.Colors.with_opacity(0.20, "#8b5cf6"),
                    ft.Colors.with_opacity(0.12, "#6366f1"),
                ],
                tile_mode=ft.GradientTileMode.CLAMP,
            ),
            border=ft.border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.WHITE)),
            border_radius=20,
            padding=ft.padding.symmetric(horizontal=16, vertical=14),
            margin=ft.margin.only(left=20, right=20, bottom=16),
            on_click=on_click,
            animate=ft.Animation(300, ft.AnimationCurve.EASE_OUT),
        )

    def _get_country_colors(self, country_code: str) -> tuple:
        """Get gradient colors for a country."""
        cc = country_code.lower() if country_code else "default"
        return FLAG_COLORS.get(cc, FLAG_COLORS["default"])

    def _update_gradient_colors(self):
        """Update gradient with current country colors."""
        from src.ui.helpers.gradient_helper import GradientHelper

        cc = self._profile.get("country_code") if hasattr(self, "_profile") and self._profile else None
        self.gradient = GradientHelper.get_flag_gradient(cc)

    def update_server(self, profile):
        """Update server card with profile data."""
        from src.core.city_translator import translate_city
        from src.core.country_translator import translate_country

        self._profile = profile  # CRITICAL: Save profile so gradient helper can find it
        if not profile:
            self._icon_container.content = self._globe_icon
            self._name_text.value = t("server_list.no_server")
            self._name_text.color = ft.Colors.ON_SURFACE_VARIANT
            self._address_text.value = ""
            self._country_city_text.value = ""
            self._current_colors = FLAG_COLORS["default"]
            self._update_gradient_colors()
        else:
            # Check if this is a chain
            is_chain = profile.get("_is_chain") or profile.get("items") is not None

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
            elif is_chain:
                # Use chain icon for chains
                chain_icon = ft.Icon(ft.Icons.LINK, size=28, color=ft.Colors.PRIMARY)
                self._icon_container.content = chain_icon
                self._current_colors = FLAG_COLORS["default"]
            else:
                self._icon_container.content = self._globe_icon
                self._current_colors = FLAG_COLORS["default"]

            # Update country/city text
            # Update country/city text
            if is_chain:
                # Show chain info but try to get exit node location
                item_count = len(profile.get("items", []))

                # Try to resolve exit node for location info
                exit_profile = None
                if profile.get("items") and self._app_context:
                    exit_id = profile["items"][-1]
                    exit_profile = self._app_context.get_profile_by_id(exit_id)

                if exit_profile:
                    # Use exit profile for location display
                    country_name = exit_profile.get("country_name") or exit_profile.get("name", "")
                    exit_cc = exit_profile.get("country_code")
                    if exit_cc:
                        country_name = translate_country(exit_cc, country_name)

                    city = exit_profile.get("city")
                    if city:
                        translated_city = translate_city(city)
                        self._country_city_text.value = f"{country_name}, {translated_city}"
                    else:
                        self._country_city_text.value = country_name
                else:
                    # Fallback to generic chain title
                    self._country_city_text.value = f"⛓ {t('chain.title')}"
            else:
                country_name = profile.get("country_name") or profile.get("name", "")
                if cc:
                    country_name = translate_country(cc, country_name)
                city = profile.get("city")
                if city:
                    translated_city = translate_city(city)
                    self._country_city_text.value = f"{country_name}, {translated_city}"
                else:
                    self._country_city_text.value = country_name

            self._name_text.value = profile["name"]
            self._name_text.color = ft.Colors.ON_SURFACE

            # Address - only for non-chain profiles
            if is_chain:
                item_count = len(profile.get("items", []))
                self._address_text.value = f"{item_count} {t('server_list.servers') if item_count != 1 else 'server'}"
            else:
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
            self.border = ft.border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE))
            self._globe_icon.color = ft.Colors.ON_SURFACE_VARIANT
            self._list_btn.bgcolor = ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
            # Safe shadow update
            if self.shadow:
                if isinstance(self.shadow, list):
                    if len(self.shadow) > 0:
                        self.shadow[0].color = ft.Colors.with_opacity(0.15, ft.Colors.BLACK)
                else:
                    self.shadow.color = ft.Colors.with_opacity(0.15, ft.Colors.BLACK)
        else:
            self.border = ft.border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE))
            self._globe_icon.color = ft.Colors.ON_SURFACE_VARIANT
            self._list_btn.bgcolor = ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)
            # Safe shadow update
            if self.shadow:
                if isinstance(self.shadow, list):
                    if len(self.shadow) > 0:
                        self.shadow[0].color = ft.Colors.with_opacity(0.08, ft.Colors.BLACK)
                else:
                    self.shadow.color = ft.Colors.with_opacity(0.08, ft.Colors.BLACK)

        self._update_gradient_colors()
        self.update()
