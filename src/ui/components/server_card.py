import flet as ft


class ServerCard(ft.UserControl):
    def __init__(self, on_click):
        super().__init__()
        self.on_click = on_click
        self._flag_text = ft.Text("🌐", size=28)
        self._name_text = ft.Text(
            "No Server Selected",
            color=ft.colors.GREY_400,
            size=14,
            weight=ft.FontWeight.BOLD,
        )
        self._address_text = ft.Text("", size=10, color=ft.colors.GREY_500)

    def build(self):
        # Determine colors based on theme (this is a bit tricky since we don't have direct access to page.theme_mode here easily without passing it down or checking page)
        # Instead, we'll use theme-aware colors that Flet resolves automatically,
        # OR we can assume the parent will trigger an update if theme changes.
        # For better control, we can check self.page.theme_mode if attached, but build() runs before attachment sometimes.
        # Let's use Flet's theme colors which auto-adapt.

        self._container = ft.Container(
            content=ft.Row(
                [
                    ft.Text("🌐", size=28),
                    ft.Column(
                        [
                            ft.Text(
                                "Current Server",
                                size=10,
                                color=ft.colors.ON_SURFACE_VARIANT,
                            ),
                            self._name_text,
                            self._address_text,
                        ],
                        expand=True,
                        spacing=2,
                    ),
                    ft.IconButton(
                        ft.icons.LIST,
                        icon_color=ft.colors.ON_SURFACE_VARIANT,
                        on_click=self.on_click,
                    ),
                ]
            ),
            bgcolor=ft.colors.SURFACE,  # Adapts: White/Light Grey in Light, Dark Grey in Dark
            border=ft.border.all(1, ft.colors.OUTLINE_VARIANT),  # Subtle border
            border_radius=15,
            padding=15,
            margin=20,
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=10,
                color=ft.colors.SHADOW,
                offset=ft.Offset(0, 2),
            ),
            on_click=self.on_click,
        )
        return self._container

    def update_server(self, profile):
        if not profile:
            self._flag_text.value = "🌐"
            self._name_text.value = "No Server Selected"
            self._name_text.color = ft.colors.ON_SURFACE_VARIANT
            self._address_text.value = ""
        else:
            self._flag_text.value = "🌐"
            self._name_text.value = profile["name"]
            self._name_text.color = ft.colors.PRIMARY

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
            self._container.bgcolor = ft.colors.SURFACE
            self._container.border.color = ft.colors.OUTLINE_VARIANT
            self._name_text.color = ft.colors.WHITE
            self._flag_text.color = ft.colors.WHITE
        else:
            self._container.bgcolor = "#ffffff"  # Explicit white for light mode
            self._container.border.color = "#e0e0e0"
            self._name_text.color = ft.colors.BLACK
            self._flag_text.color = ft.colors.BLACK
        self.update()
