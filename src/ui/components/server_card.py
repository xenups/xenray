import flet as ft


class ServerCard(ft.Container):
    def __init__(self, on_click):
        self._flag_text = ft.Text("🌐", size=28)
        self._name_text = ft.Text("No Server Selected", color=ft.Colors.GREY_400, size=14, weight=ft.FontWeight.BOLD)
        self._address_text = ft.Text("", size=10, color=ft.Colors.GREY_500)

        super().__init__(
            content=ft.Row([
                ft.Text("🌐", size=28),
                ft.Column([
                    ft.Text("Current Server", size=10, color=ft.Colors.ON_SURFACE_VARIANT),
                    self._name_text,
                    self._address_text
                ], expand=True, spacing=2),
                ft.IconButton(ft.Icons.LIST, icon_color=ft.Colors.ON_SURFACE_VARIANT, on_click=on_click)
            ]),
            bgcolor=ft.Colors.SURFACE, # Adapts: White/Light Grey in Light, Dark Grey in Dark
            border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT), # Subtle border
            border_radius=15,
            padding=15,
            margin=ft.margin.only(left=20, right=20, bottom=20),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=10,
                color=ft.Colors.SHADOW,
                offset=ft.Offset(0, 2),
            ),
            on_click=on_click
        )

    def update_server(self, profile):
        if not profile:
            self._flag_text.value = "🌐"
            self._name_text.value = "No Server Selected"
            self._name_text.color = ft.Colors.ON_SURFACE_VARIANT
            self._address_text.value = ""
        else:
            self._flag_text.value = "🌐"
            self._name_text.value = profile["name"]
            self._name_text.color = ft.Colors.PRIMARY
            
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
            self._flag_text.color = ft.Colors.WHITE
            # Fix: Ensure name text color is reset for dark mode
            self._name_text.color = ft.Colors.PRIMARY 
            self.shadow.color = ft.Colors.SHADOW
            self.shadow.blur_radius = 10
            self.shadow.spread_radius = 1
        else:
            self.bgcolor = "#ffffff" # Explicit white for light mode
            self.border.color = "#e0e0e0"
            self._name_text.color = ft.Colors.BLACK
            self._flag_text.color = ft.Colors.BLACK
            # Reduced shadow for light mode
            self.shadow.color = ft.Colors.with_opacity(0.1, ft.Colors.BLACK)
            self.shadow.blur_radius = 5
            self.shadow.spread_radius = 0
        self.update()
