from __future__ import annotations
import flet as ft
import socket
import threading
import time
from typing import Callable, Optional

# فرض بر این است که این ماژول‌ها در ساختار پروژه شما موجودند
from src.core.config_manager import ConfigManager
from src.utils.link_parser import LinkParser


class ServerList(ft.Container):
    """Thread-safe Server List component for XenRay."""

    def __init__(self, config_manager: ConfigManager, on_server_selected: Callable):
        self._config_manager = config_manager
        self._on_server_selected = on_server_selected
        self._profiles: list[dict] = []
        self._page: Optional[ft.Page] = None

        # Header
        self._header = ft.Row(
            [
                ft.Text("Servers", size=20, weight=ft.FontWeight.BOLD),
                ft.IconButton(ft.Icons.ADD, on_click=self._show_add_dialog), # فراخوانی متد باز کردن دیالوگ
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # List View
        self._list_view = ft.ListView(expand=True, spacing=10, padding=10)

        # Add Dialog
        self._link_input = ft.TextField(
            label="VLESS Link", 
            multiline=True, 
            min_lines=3, 
            text_size=12,
            max_lines=10, # اضافه شده برای ظاهر بهتر
        )
        self._add_dialog = ft.AlertDialog(
            title=ft.Text("Add Server"),
            content=self._link_input,
            actions=[
                ft.TextButton("Add", on_click=self._add_server),
                ft.TextButton("Cancel", on_click=self._close_dialog),
            ],
            actions_alignment=ft.MainAxisAlignment.END, # اضافه شده برای ظاهر بهتر
        )

        super().__init__(
            content=ft.Column(
                [
                    self._header,
                    ft.Divider(),
                    self._list_view,
                ]
            ),
            padding=10,
            expand=True,
        )

    # -----------------------------
    # Page setter
    # -----------------------------
    def set_page(self, page: ft.Page):
        self._page = page
        # اضافه کردن دیالوگ به page در اینجا اختیاری است اما مطمئن‌تر است
        # self._page.dialog = self._add_dialog 
        threading.Thread(target=self._wait_until_added_and_load, daemon=True).start()

    def _wait_until_added_and_load(self):
        while not self._page or not self.page: # بررسی self.page هم برای Flet لازم است
            time.sleep(0.05)
        self._load_profiles(update_ui=True)

    # -----------------------------
    # Thread-safe UI helper
    # -----------------------------
    def _ui(self, fn: Callable):
        if not self._page:
            return
        async def _coro():
            try:
                fn()
            except Exception as e:
                # استفاده از page.open() برای نمایش خطای UI
                if self._page:
                    self._page.open(ft.SnackBar(
                        content=ft.Text(f"UI update error: {e}"),
                        bgcolor=ft.colors.RED_700
                    ))
                    self._page.update()
                print(f"UI update error: {e}")
        self._page.run_task(_coro)

    # -----------------------------
    # Load / refresh profiles
    # -----------------------------
    def _load_profiles(self, update_ui=False):
        self._profiles = self._config_manager.load_profiles()
        self._list_view.controls.clear()

        for profile in self._profiles:
            self._list_view.controls.append(self._create_server_item(profile))

        if update_ui:
            self._ui(lambda: self.update())

    # -----------------------------
    # Create server row
    # -----------------------------
    def _create_server_item(self, profile: dict):
        config = profile.get("config", {})
        address, port = self._extract_address_port(config)

        # برچسب برای نمایش پینگ
        ping_label = ft.Text("...", size=12, color=ft.Colors.GREY_500)

        # Start ping thread
        if self._page:
            threading.Thread(target=self._ping_thread, args=(address, port, ping_label), daemon=True).start()

        return ft.Container(
            content=ft.Row(
                [
                    ft.Text("🌐", size=24),
                    ft.Column(
                        [
                            ft.Text(profile["name"], weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
                            ft.Row(
                                [
                                    ft.Text(f"{address}:{port}", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                                    ping_label,
                                ],
                                spacing=10,
                            ),
                        ],
                        expand=True,
                        spacing=2,
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE,
                        icon_color=ft.Colors.RED_400,
                        on_click=lambda e, pid=profile["id"]: self._delete_server(pid),
                    ),
                ]
            ),
            padding=15,
            border_radius=10,
            bgcolor=ft.Colors.SURFACE,
            border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
            on_click=lambda e, p=profile: self._select_server(p),
            ink=True,
        )

    def _extract_address_port(self, config: dict):
        outbounds = config.get("outbounds", [])
        for outbound in outbounds:
            protocol = outbound.get("protocol")
            if protocol in ["vless", "vmess", "trojan", "shadowsocks"]:
                settings = outbound.get("settings", {})
                if "vnext" in settings and settings["vnext"]:
                    server = settings["vnext"][0]
                    return server.get("address", "Unknown"), server.get("port", "N/A")
                elif "servers" in settings and settings["servers"]:
                    server = settings["servers"][0]
                    return server.get("address", "Unknown"), server.get("port", "N/A")
        return "Unknown", "N/A"

    # -----------------------------
    # Ping server
    # -----------------------------
    def _ping_thread(self, address, port, label: ft.Text):
        if address == "Unknown" or port == "N/A":
            self._ui(lambda: self._update_label(label, "N/A", ft.Colors.GREY_500))
            return

        # پینگ در Flet باید با تایم‌آوت کوتاه و تلاش‌های محدود انجام شود
        max_retries = 3 
        timeout = 2
        
        for _ in range(max_retries):
            try:
                start = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                # اطمینان از اینکه پورت یک عدد است
                result = sock.connect_ex((address, int(port)))
                sock.close()
                latency = int((time.time() - start) * 1000)
                
                if result == 0:
                    self._ui(lambda: self._update_label(label, f"{latency}ms", ft.Colors.GREEN_400))
                    return
            except Exception:
                pass
            time.sleep(0.5) # کمی صبر قبل از تلاش مجدد

        self._ui(lambda: self._update_label(label, "Timeout", ft.Colors.RED_400))

    def _update_label(self, label: ft.Text, text: str, color):
        label.value = text
        label.color = color
        try:
            label.update()
        except Exception:
            # اگر کنترلر به صفحه متصل نباشد، این خطا رخ می‌دهد
            pass

    # -----------------------------
    # Add / Delete server
    # -----------------------------
    def _show_add_dialog(self, e):
        # 🟢 FIX: اطمینان از تنظیم page و استفاده از الگوی استاندارد
        if not self._page:
            return
            
        self._page.open(self._add_dialog)
        self._page.update()

    def _close_dialog(self, e):
        # 🟢 FIX: استفاده از الگوی استاندارد و پاک کردن ورودی
        if not self._page:
            return
            
        self._page.close(self._add_dialog)
        self._link_input.value = "" 
        self._link_input.error_text = None
        
        self._page.update()

    def _add_server(self, e):
        link = self._link_input.value.strip()
        if not link:
            return
            
        if not self._page:
            return

        try:
            parsed = LinkParser.parse_vless(link)
            self._config_manager.save_profile(parsed["name"], parsed["config"])
            
            # بستن دیالوگ و پاک کردن فیلد
            self._close_dialog(None)
            
            # به‌روزرسانی لیست و نمایش پیام موفقیت
            self._load_profiles(update_ui=True)
            self._page.open(ft.SnackBar(
                content=ft.Text(f"Server '{parsed['name']}' added successfully. 🥳")
            ))
            self._page.update() 
            
        except Exception as ex:
            # نمایش خطا در فیلد ورودی
            self._link_input.error_text = f"Invalid link: {ex}"
            self._page.update() # به‌روزرسانی برای نمایش پیام خطا در فیلد ورودی

    def _delete_server(self, profile_id):
        self._config_manager.delete_profile(profile_id)
        self._load_profiles(update_ui=True)
        # 🟢 اضافه کردن Snackbar برای تأیید حذف
        if self._page:
            self._page.open(ft.SnackBar(
                content=ft.Text("Server deleted successfully. 🗑️")
            ))
            self._page.update()

    # -----------------------------
    # Select server
    # -----------------------------
    def _select_server(self, profile):
        if self._on_server_selected:
            self._on_server_selected(profile)