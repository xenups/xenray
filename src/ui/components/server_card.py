import flet as ft

from src.core.i18n import t


class ServerCard(ft.Container):
    def __init__(self, on_click):
        # Icon Container (Holds Flag or Globe)
        # Use Icon instead of emoji for consistent sizing
        self._globe_icon = ft.Icon(
            ft.Icons.PUBLIC,
            size=18,
            color=ft.Colors.ON_SURFACE_VARIANT
        )
        self._icon_container = ft.Container(
            content=self._globe_icon,
            width=32, height=32,
            alignment=ft.alignment.center,
            border_radius=16,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=4,
                color=ft.Colors.with_opacity(0.2, ft.Colors.BLACK),
                offset=ft.Offset(0, 1),
            ),
        )

        self._name_text = ft.Text(
            t("server_list.no_server"),
            color=ft.Colors.GREY_400,
            size=14,
            weight=ft.FontWeight.BOLD,
        )
        self._address_text = ft.Text("", size=10, color=ft.Colors.GREY_500)

        super().__init__(
            content=ft.Row(
                [
                    self._icon_container,
                    ft.Column(
                        [
                            ft.Text(
                                t("server_list.current_server"),
                                size=10,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            self._name_text,
                            self._address_text,
                        ],
                        expand=True,
                        spacing=2,
                    ),
                    ft.IconButton(
                        ft.Icons.LIST,
                        icon_color=ft.Colors.ON_SURFACE_VARIANT,
                        on_click=on_click,
                    ),
                ]
            ),
            bgcolor=ft.Colors.SURFACE,  # Adapts: White/Light Grey in Light, Dark Grey in Dark
            border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),  # Subtle border
            border_radius=15,
            padding=15,
            margin=ft.margin.only(left=20, right=20, bottom=20),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=10,
                color=ft.Colors.SHADOW,
                offset=ft.Offset(0, 2),
            ),
            on_click=on_click,
        )

    def update_server(self, profile):
        if not profile:
            self._icon_container.content = self._globe_icon
            self._icon_container.update()
            
            self._name_text.value = t("server_list.no_server")
            self._name_text.color = ft.Colors.ON_SURFACE_VARIANT
            self._address_text.value = ""
        else:
            # Check for flag
            cc = profile.get("country_code")
            if cc:
                # Create fresh image with anti-aliasing and border radius for smooth rendering
                new_image = ft.Image(
                    src=f"/flags/{cc.lower()}.svg",
                    width=32,
                    height=32,
                    fit=ft.ImageFit.COVER,
                    gapless_playback=True,
                    filter_quality=ft.FilterQuality.HIGH,
                    border_radius=ft.border_radius.all(16),
                    anti_alias=True
                )
                self._icon_container.content = new_image
                self._icon_container.tooltip = profile.get("country_name", cc)
                self._icon_container.update()
            else:
                self._icon_container.content = self._globe_icon
                self._icon_container.update()

            self._name_text.value = profile["name"]
            self._name_text.color = ft.Colors.PRIMARY
            
            # ... Address logic ...
            try:
                vnext = profile["config"]["outbounds"][0]["settings"]["vnext"][0]
                address = vnext["address"]
                port = vnext["port"]
                self._address_text.value = f"{address}:{port}"
            except:
                self._address_text.value = ""

        self.update()

    def update_theme(self, is_dark: bool):
        if is_dark:
            self.bgcolor = ft.Colors.SURFACE
            self.border.color = ft.Colors.OUTLINE_VARIANT
            self._globe_icon.color = ft.Colors.ON_SURFACE_VARIANT
            # Fix: Ensure name text color is reset for dark mode
            self._name_text.color = ft.Colors.PRIMARY
            self.shadow.color = ft.Colors.SHADOW
            self.shadow.blur_radius = 10
            self.shadow.spread_radius = 1
        else:
            self.bgcolor = "#ffffff"  # Explicit white for light mode
            self.border.color = "#e0e0e0"
            self._name_text.color = ft.Colors.BLACK
            self._globe_icon.color = ft.Colors.ON_SURFACE_VARIANT
            # Reduced shadow for light mode
            self.shadow.color = ft.Colors.with_opacity(0.1, ft.Colors.BLACK)
            self.shadow.blur_radius = 5
            self.shadow.spread_radius = 0
        self.update()
