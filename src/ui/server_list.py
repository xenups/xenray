from __future__ import annotations
import flet as ft
import socket
import threading
import time
from typing import Callable, Optional
from src.core.config_manager import ConfigManager
from src.utils.link_parser import LinkParser
from src.core.subscription_manager import SubscriptionManager
from src.services.connection_tester import ConnectionTester


class ServerList(ft.Container):
    """Thread-safe Server List component for XenRay."""

    def __init__(self, config_manager: ConfigManager, on_server_selected: Callable):
        self._config_manager = config_manager
        self._subscription_manager = SubscriptionManager(config_manager)
        self._on_server_selected = on_server_selected
        
        # Data
        self._profiles: list[dict] = []
        self._subscriptions: list[dict] = []
        
        # State
        self._page: Optional[ft.Page] = None
        self._current_list_view = None
        self._ping_queue = [] # Queue for manual ping test
        self._is_testing = False
        self._cancel_testing = False # Flag to abort testing
        self._selected_profile_id = None # Track selected profile
        self._active_subscription = None # Track if we are inside a subscription
        
        # Ping Cache: {profile_id: (text, color, latency_val)}
        # To persist state during sorting reloads and view switches
        self._ping_state_cache = {}

        # Header
        self._header_container = ft.Container(padding=0)

        # Animated Body Switcher
        self._body_switcher = ft.AnimatedSwitcher(
            content=ft.Container(),
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=150,
            reverse_duration=150,
            switch_in_curve=ft.AnimationCurve.EASE_IN,
            switch_out_curve=ft.AnimationCurve.EASE_OUT,
        )

        # Dialogs
        self._setup_dialogs()

        super().__init__(
            content=ft.Column(
                [
                    self._header_container,
                    ft.Container(height=5),
                    ft.Container(content=self._body_switcher, expand=True),
                ],
                spacing=0,
            ),
            padding=5,
            bgcolor=ft.Colors.TRANSPARENT,
            expand=True,
        )

        # Initialize header content
        self._show_main_header()

    def _setup_dialogs(self):
        # Unified Add Dialog
        self._add_name_input = ft.TextField(
            label="Name (Optional for Config)",
            hint_text="Required for Subscriptions",
            text_size=12
        )
        self._add_content_input = ft.TextField(
            label="Link / URL",
            hint_text="vless://... or https://example.com/sub",
            multiline=True,
            min_lines=3,
            max_lines=10,
            text_size=12,
        )
        
        self._unified_add_dialog = ft.AlertDialog(
            title=ft.Text("Add Server or Subscription"),
            content=ft.Column([self._add_name_input, self._add_content_input], height=180),
            actions=[
                ft.TextButton("Add", on_click=self._handle_unified_add),
                ft.TextButton("Cancel", on_click=self._close_unified_dialog),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    # -----------------------------
    # Header & Menus
    # -----------------------------
    def _update_header(self):
        """Refreshes the header based on current state (Active Sub vs Main)."""
        if self._active_subscription:
            self._show_subscription_header(self._active_subscription)
        else:
            self._show_main_header()

    def _create_sort_menu(self):
        current_sort = self._config_manager.get_sort_mode()
        
        def set_sort(mode):
            self._config_manager.set_sort_mode(mode)
            # Update Header IMMEDIATELY to reflect checkmark change
            self._update_header()
            # Reload list to reflect sort
            self._load_profiles(update_ui=True)

        return ft.PopupMenuButton(
            icon=ft.Icons.SORT,
            tooltip="Sort",
            items=[
                ft.PopupMenuItem(
                    text="Name (A-Z)",
                    checked=current_sort == "name_asc",
                    on_click=lambda e: set_sort("name_asc")
                ),
                ft.PopupMenuItem(
                    text="Latency (Low-High)",
                    checked=current_sort == "ping_asc",
                    on_click=lambda e: set_sort("ping_asc")
                ),
            ]
        )

    def _show_main_header(self):
        self._header_container.content = ft.Row(
            [
                ft.Text("Servers", size=20, weight=ft.FontWeight.BOLD),
                ft.Row(
                    [
                        ft.IconButton(
                            ft.Icons.SPEED,
                            tooltip="Test Latency",
                            on_click=lambda e: self._test_all_latencies(),
                        ),
                        self._create_sort_menu(),
                        
                        # Unified Add Button
                        ft.IconButton(
                            ft.Icons.ADD,
                            tooltip="Add Server/Subscription",
                            on_click=self._show_unified_add_dialog,
                        ),
                    ]
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        if self._page:
            self._header_container.update()

    def _show_subscription_header(self, sub: dict):
        self._header_container.content = ft.Row(
            [
                ft.Row(
                    [
                        ft.IconButton(
                            ft.Icons.ARROW_BACK,
                            on_click=lambda e: self._exit_subscription_view(),
                        ),
                        ft.Text(sub["name"], size=20, weight=ft.FontWeight.BOLD),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row([
                    ft.IconButton(
                        ft.Icons.SPEED,
                        tooltip="Test Latency",
                        on_click=lambda e: self._test_all_latencies(),
                    ),
                    self._create_sort_menu(),

                    ft.PopupMenuButton(
                        icon=ft.Icons.MORE_VERT,
                        items=[
                            ft.PopupMenuItem(
                                text="Update Subscription",
                                icon=ft.Icons.REFRESH,
                                on_click=lambda e: self._update_subscription(sub["id"]),
                            ),
                            ft.PopupMenuItem(
                                text="Delete Subscription",
                                icon=ft.Icons.DELETE,
                                on_click=lambda e: self._delete_and_exit_subscription(
                                    sub["id"]
                                ),
                            ),
                        ],
                    ),
                ])
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        if self._page:
            self._header_container.update()

    # -----------------------------
    # Page setter
    # -----------------------------
    def set_page(self, page: ft.Page):
        self._page = page
        threading.Thread(target=self._wait_until_added_and_load, daemon=True).start()

    def _wait_until_added_and_load(self):
        while not self._page or not self.page:
            time.sleep(0.05)
        self._load_profiles(update_ui=True)

    def _ui(self, fn: Callable):
        if not self._page:
            return
        async def _coro():
            try:
                fn()
            except Exception as e:
                print(f"UI update error: {e}")
        self._page.run_task(_coro)

    # -----------------------------
    # Load / Sort / Refresh Profiles
    # -----------------------------
    def _apply_sort(self, items: list) -> list:
        mode = self._config_manager.get_sort_mode()
        
        # Helper to get cached latency for sorting
        def get_latency(item):
            pid = item.get("id")
            if pid in self._ping_state_cache:
                return self._ping_state_cache[pid][2] # latency_val
            return 999999

        if mode == "name_asc":
            return sorted(items, key=lambda x: x.get("name", "").lower())
        
        if mode == "ping_asc":
             return sorted(items, key=get_latency)
             
        # Catch others
        return items

    def _load_profiles(self, update_ui=False):
        # When reloading, ensure we stop any pending tests if we are switching contexts
        # (Though _load_profiles is also called during sort... we probably don't want to cancel sort refresh)
        # But if we are switching views, we should called cancellation manually.
        
        def _task():
            # Reload from disk
            self._profiles = self._config_manager.load_profiles()
            self._subscriptions = self._config_manager.load_subscriptions()
            
            # Sort subscriptions by name always
            self._subscriptions.sort(key=lambda x: x.get("name", "").lower())

            # If we are currently inside a subscription, we need to refresh THAT view
            # instead of resetting to the main list.
            if self._active_subscription:
                 # Find the fresh version of this subscription
                 # IMPORTANT: Use ID comparison
                 fresh_sub = next((s for s in self._subscriptions if s["id"] == self._active_subscription["id"]), None)
                 
                 if fresh_sub:
                     # Re-enter (refresh) sub view
                     if update_ui:
                        self._ui(lambda: self._enter_subscription_view(fresh_sub))
                     else:
                        self._enter_subscription_view(fresh_sub)
                     return # EARLY RETURN! Do not build main list.

            # --- Main List Logic ---
            
            # Sort profiles
            self._profiles = self._apply_sort(self._profiles)

            # Create components
            new_list_view = ft.ListView(expand=True, spacing=5, padding=5)
            
            self._available_ping_targets = [] 
            
            # Subscriptions
            for sub in self._subscriptions:
                new_list_view.controls.append(self._create_subscription_item(sub))

            # Profiles
            for profile in self._profiles:
                control, ping_label = self._create_server_item(profile)
                new_list_view.controls.append(control)
                self._available_ping_targets.append((profile, ping_label))

            # Switch view
            def _update():
                old_view = self._current_list_view
                self._current_list_view = new_list_view
                self._body_switcher.content = new_list_view
                self._body_switcher.update()
                if old_view:
                    del old_view
            
            if update_ui:
                self._ui(_update)
            else:
                self._current_list_view = new_list_view
                self._body_switcher.content = new_list_view

        if update_ui:
            threading.Thread(target=_task, daemon=True).start()
        else:
            _task()

    # -----------------------------
    # Create Item
    # -----------------------------
    def _create_server_item(self, profile: dict, read_only=False):
        """Returns (ContainerControl, PingLabelControl)"""
        config = profile.get("config", {})
        address, port = self._extract_address_port(config)

        # Restore from cache if available
        pid = profile.get("id")
        last_ping = "..."
        last_ping_color = ft.Colors.GREY_500
        
        # DEBUG: Ping Persistence Check
        # If we have a cached value, use it.
        if pid in self._ping_state_cache:
            last_ping, last_ping_color, _ = self._ping_state_cache[pid]
        
        # Check selection state
        is_selected = (self._selected_profile_id == pid)
        
        # Determine Border
        if is_selected:
            # Highlight border for selected item
            border_color = ft.Colors.PRIMARY
            border_width = 2
            bg_color = ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY) # Light tint
        else:
            border_color = ft.Colors.with_opacity(0.5, ft.Colors.OUTLINE_VARIANT) if read_only else ft.Colors.OUTLINE_VARIANT
            border_width = 1
            bg_color = ft.Colors.SURFACE
        
        ping_label = ft.Text(last_ping, size=12, color=last_ping_color, weight=ft.FontWeight.BOLD)

        # Elements
        
        # Left Side: Icon + Info
        left_content = ft.Row(
            [
                ft.Text("🌐", size=24),
                ft.Column(
                    [
                        ft.Text(
                            profile["name"],
                            weight=ft.FontWeight.BOLD,
                            size=14,
                            color=ft.Colors.ON_SURFACE,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            f"{address}:{port}",
                            size=11,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=2,
                )
            ],
            spacing=10,
            expand=True,
        )

        # Right Side: Ping Label + (Delete Button)
        right_controls = [ping_label]
        
        if not read_only:
             right_controls.append(
                ft.IconButton(
                    ft.Icons.DELETE,
                    icon_color=ft.Colors.RED_400,
                    tooltip="Delete Server",
                    on_click=lambda e, pid=profile["id"]: self._delete_server(pid),
                )
            )
            
        right_content = ft.Row(right_controls, spacing=5, alignment=ft.MainAxisAlignment.END)

        container = ft.Container(
            content=ft.Row(
                [left_content, right_content], 
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
            border_radius=8,
            bgcolor=bg_color,
            border=ft.border.all(border_width, border_color),
            on_click=lambda e, p=profile: self._select_server(p),
            ink=True,
        )
        return container, ping_label

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
    # Latency Testing
    # -----------------------------
    def _test_all_latencies(self):
        """Trigger manual latency test for all visible items."""
        if self._is_testing:
            if self._page:
                self._page.open(ft.SnackBar(content=ft.Text("Test already in progress...")))
                self._page.update()
            return
            
        targets = getattr(self, "_available_ping_targets", [])
        if not targets:
            return

        self._is_testing = True
        self._cancel_testing = False # Reset cancel flag
        
        if self._page:
            self._page.open(ft.SnackBar(content=ft.Text("Started latency test... 🚀")))
            self._page.update()

        def _run_tests():
            for profile, label in targets:
                if self._cancel_testing:
                    break # Abort if canceled
                
                # Update label to "Testing..."
                self._ui(lambda: self._update_label(label, "Testing...", ft.Colors.BLUE_400))
                
                # Run Connection Test (Synchronous inside this thread)
                success, result = ConnectionTester.test_connection_sync(profile["config"])
                
                # Update UI result
                color = ft.Colors.GREEN_400 if success else ft.Colors.RED_400
                self._ui(lambda: self._update_label(label, result, color))
                
                # Cache result
                latency_val = 999999
                if success and "ms" in result:
                     try:
                        latency_val = int(result.replace("ms", ""))
                     except:
                        pass
                
                # Update Cache
                pid = profile.get("id")
                if pid:
                    self._ping_state_cache[pid] = (result, color, latency_val)
                
                # Small delay to prevent CPU spike
                time.sleep(0.1)
            
            self._is_testing = False
            self._ui(lambda: self._page.update() if self._page else None)

        threading.Thread(target=_run_tests, daemon=True).start()

    def _update_label(self, label: ft.Text, text: str, color):
        label.value = text
        label.color = color
        try:
            label.update()
        except Exception:
            pass

    # -----------------------------
    # Subscription UI (Folder View Legacy)
    # -----------------------------
    def _create_subscription_item(self, sub: dict):
        profiles = sub.get("profiles", [])
        return ft.Container(
            content=ft.ListTile(
                leading=ft.Icon(ft.Icons.FOLDER, color=ft.Colors.PRIMARY, size=24),
                title=ft.Text(sub["name"], weight=ft.FontWeight.BOLD, size=14),
                subtitle=ft.Text(f"{len(profiles)} servers • {sub['url'][:30]}...", size=11, color=ft.Colors.GREY_500),
                trailing=ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=14, color=ft.Colors.GREY_400),
                on_click=lambda e: self._enter_subscription_view(sub),
                dense=True,
                content_padding=ft.padding.symmetric(horizontal=5, vertical=0),
            ),
            padding=0,
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY),
            border=ft.border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.PRIMARY)),
            margin=ft.margin.only(bottom=2),
        )

    def _enter_subscription_view(self, sub: dict):
        # Cancel any previous tests to prevent cross-view pollution
        self._cancel_testing = True
        
        # State Tracking
        self._active_subscription = sub
        
        self._show_subscription_header(sub)
        
        profiles = sub.get("profiles", [])
        
        # Apply Sort
        profiles = self._apply_sort(profiles)
        
        sub_list_view = ft.ListView(expand=True, spacing=5, padding=5)
        self._available_ping_targets = []
        
        for profile in profiles:
            control, ping_label = self._create_server_item(profile, read_only=True)
            sub_list_view.controls.append(control)
            self._available_ping_targets.append((profile, ping_label))

        self._current_list_view = sub_list_view
        self._body_switcher.content = sub_list_view
        self._body_switcher.update()

    def _exit_subscription_view(self):
        # Cancel active tests from subscription view
        self._cancel_testing = True
        
        self._active_subscription = None # Clear state
        self._show_main_header()
        self._load_profiles(update_ui=True)

    def _delete_and_exit_subscription(self, sub_id):
        self._delete_subscription(sub_id)
        self._active_subscription = None
        self._show_main_header()

    # -----------------------------
    # Unified Add Action
    # -----------------------------
    def _handle_unified_add(self, e):
        content = self._add_content_input.value.strip()
        name = self._add_name_input.value.strip()
        
        if not content:
            self._add_content_input.error_text = "Required"
            self._add_content_input.update()
            return

        if not self._page: return

        # HEURISTIC 1: Try parse as VLESS/VMESS config
        # Common prefixes
        is_config = content.startswith(("vless://", "vmess://", "trojan://", "ss://"))
        
        # Or if the parser can handle it (deep check)
        # But we'll try/except the parser first
        
        config_success = False
        try:
            # We assume LinkParser exists and works. If it fails, we fall back to Subscription
            # BUT: Subscription URLs might look like normal URLs used in VLESS path? No.
            # If LinkParser succeeds, it's definitely a server.
            parsed = LinkParser.parse_vless(content)
            # If name provided by user, override
            final_name = name if name else parsed["name"]
            
            self._config_manager.save_profile(final_name, parsed["config"])
            config_success = True
            
            self._page.open(ft.SnackBar(content=ft.Text(f"Server '{final_name}' added! 🚀", color=ft.Colors.GREEN_400)))
            
        except Exception:
            # Not a valid server link (or parser failed).
            # HEURISTIC 2: Treat as Subscription
            # Subscriptions usually need a name. If empty, we can't do much.
            if not name:
                self._add_name_input.error_text = "Name required for Subscription"
                self._add_name_input.update()
                # If it looked like a VLESS link but failed, user might be confused.
                if is_config:
                     self._page.open(ft.SnackBar(content=ft.Text("Invalid Server Link", color=ft.Colors.RED_400)))
                return

            self._config_manager.save_subscription(name, content)
            self._page.open(ft.SnackBar(content=ft.Text(f"Subscription '{name}' added! 📂", color=ft.Colors.GREEN_400)))
            config_success = True # Well, sub success.

        if config_success:
            self._close_unified_dialog(None)
            self._load_profiles(update_ui=True)
            self._page.update()

    def _update_subscription(self, sub_id):
        if not self._page:
            return
        self._page.open(ft.SnackBar(content=ft.Text("Updating subscription...")))
        self._page.update()

        def callback(success, msg):
            def _ui_update():
               if success:
                   self._page.open(ft.SnackBar(content=ft.Text(msg, color=ft.Colors.GREEN_400)))
                   self._load_profiles(update_ui=True)
               else:
                   self._page.open(ft.SnackBar(content=ft.Text(f"Update failed: {msg}", color=ft.Colors.RED_400)))
               self._page.update()
            self._ui(lambda: _ui_update())

        self._subscription_manager.update_subscription(sub_id, callback)

    def _delete_subscription(self, sub_id):
        self._config_manager.delete_subscription(sub_id)
        self._load_profiles(update_ui=True)
        if self._page:
            self._page.open(ft.SnackBar(content=ft.Text("Subscription deleted")))
            self._page.update()

    def _delete_server(self, profile_id):
        self._config_manager.delete_profile(profile_id)
        self._load_profiles(update_ui=True)
        if self._page:
            self._page.open(ft.SnackBar(content=ft.Text("Server deleted successfully. 🗑️")))
            self._page.update()

    def _select_server(self, profile):
        self._selected_profile_id = profile["id"]
        
        if self._on_server_selected:
            self._on_server_selected(profile)
            
        # Refresh UI to show highlight
        # Since we might be in main view OR sub view, we call _load_profiles.
        # _load_profiles is smart enough now to reload current active sub if set.
        self._load_profiles(update_ui=True)

    # Dialog helpers
    def _show_unified_add_dialog(self, e):
        if self._page:
            self._page.open(self._unified_add_dialog)
            self._page.update()

    def _close_unified_dialog(self, e):
        if self._page:
            self._page.close(self._unified_add_dialog)
            self._add_name_input.value = ""
            self._add_content_input.value = ""
            self._add_name_input.error_text = None
            self._add_content_input.error_text = None
            self._page.update()
    
    # Legacy helpers (kept for safety if anything calls them, but unused now)
    def _show_add_sub_dialog(self, e):
        self._show_unified_add_dialog(e)
    def _close_sub_dialog(self, e):
        self._close_unified_dialog(e)
    def _show_add_dialog(self, e):
        self._show_unified_add_dialog(e)
    def _close_dialog(self, e):
        self._close_unified_dialog(e)
