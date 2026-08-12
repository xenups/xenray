"""Thread-safe Server List component for XenRay.

Light layout orchestrator: owns the ListView/Stack container, the header, the
add-server modal (Layer 1), and list-level modal toggling. Item cards, profile
loading, latency testing, subscription-folder navigation, auto-inspection
updates, sort logic, chain management and list mutations live in dedicated
single-responsibility mixins.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

import flet as ft

from src.core.app_context import AppContext
from src.core.event_bus import (
    TOPIC_INSPECTION_BATCH_COMPLETED,
    TOPIC_SERVER_INSPECTED,
    TOPIC_SERVER_INSPECTING,
    event_bus,
)
from src.core.logger import logger
from src.core.subscription_manager import SubscriptionManager
from src.services.latency_tester import LatencyTester
from src.ui.components.servers.add_server_dialog import AddServerModalContainer
from src.ui.components.servers.server_list_actions import ServerListActionsMixin
from src.ui.components.servers.server_list_chains import ServerListChainsMixin
from src.ui.components.servers.server_list_events import ServerListEventsMixin
from src.ui.components.servers.server_list_header import ServerListHeader
from src.ui.components.servers.server_list_item import ServerListItem
from src.ui.components.servers.server_list_latency import ServerListLatencyMixin
from src.ui.components.servers.server_list_loader import ServerListLoaderMixin
from src.ui.components.servers.server_list_sort import ServerListSortMixin
from src.ui.components.servers.server_list_subscriptions import (
    ServerListSubscriptionMixin,
)


class ServerList(
    ServerListLoaderMixin,
    ServerListSortMixin,
    ServerListEventsMixin,
    ServerListLatencyMixin,
    ServerListSubscriptionMixin,
    ServerListChainsMixin,
    ServerListActionsMixin,
    ft.Container,
):
    """Thread-safe Server List component for XenRay."""

    def __init__(
        self,
        app_context: AppContext,
        on_server_selected: Callable,
        on_profile_updated: Callable = None,
        toast_manager=None,
        navigate_to: Callable = None,
        navigate_back: Callable = None,
        close_sheet: Callable = None,
    ):
        self._app_context = app_context
        self._subscription_manager = SubscriptionManager(app_context)
        self._on_server_selected = on_server_selected
        self._on_profile_updated = on_profile_updated
        self._toast = toast_manager
        self._navigate_to = navigate_to
        self._navigate_back = navigate_back
        self._close_sheet = close_sheet

        # Data
        self._profiles: list[dict] = []
        self._subscriptions: list[dict] = []
        self._chains: list[dict] = []

        # State
        self._page: Optional[ft.Page] = None
        self._current_list_view = None
        self._selected_profile_id = self._app_context.settings.get_last_selected_profile_id()  # Load last selected
        self._active_subscription = None
        self._search_query = ""

        # Item tracking for updates
        self._item_map: dict[str, ServerListItem] = {}

        # Server ids with an inspection currently in flight (drives the neon
        # sweep animation on config cards even before the card is mounted).
        self._inspecting_ids: set[str] = set()

        # Latency Tester
        self._latency_tester = LatencyTester(
            on_test_start=self._on_latency_test_start,
            on_test_complete=self._on_latency_test_complete,
            on_all_complete=self._on_all_latency_tests_complete,
            app_context=self._app_context,
        )

        # Live updates for auto-inspected (newly imported) servers.
        event_bus.subscribe(TOPIC_SERVER_INSPECTED, self._on_server_inspected)
        event_bus.subscribe(TOPIC_SERVER_INSPECTING, self._on_server_inspecting)
        event_bus.subscribe(TOPIC_INSPECTION_BATCH_COMPLETED, self._on_inspection_batch_completed)

        # Header Component
        self._header = ServerListHeader(
            get_sort_mode=self._app_context.settings.get_sort_mode,
            set_sort_mode=self._on_sort_changed,
            on_test_latency=self._test_all_latencies,
            on_cancel_ping=self._cancel_ping_all,
            on_add_click=self._show_add_dialog,
            on_back_click=self._exit_subscription_view,
            on_update_subscription=self._update_subscription,
            on_delete_subscription=self._delete_and_exit_subscription,
        )

        # Add Modal (custom in-page Stack overlay — Layer 1). Toggling its
        # `visible` never touches the server list (Layer 0) or page._dialogs.
        self._add_modal = AddServerModalContainer(
            on_server_added=self._handle_server_added,
            on_subscription_added=self._handle_subscription_added,
            on_close=self._close_add_dialog,
            on_create_chain=self.show_chain_builder,
        )

        # Animated Body Switcher
        self._body_switcher = ft.AnimatedSwitcher(
            content=ft.Container(),
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=150,
            reverse_duration=150,
            switch_in_curve=ft.AnimationCurve.EASE_IN,
            switch_out_curve=ft.AnimationCurve.EASE_OUT,
            expand=True,
        )

        super().__init__(
            content=ft.Stack(
                [
                    ft.Column(
                        [
                            self._header,
                            ft.Container(height=5),
                            ft.Container(content=self._body_switcher, expand=True),
                        ],
                        spacing=0,
                    ),
                    self._add_modal,
                ],
                expand=True,
            ),
            padding=5,
            bgcolor=ft.Colors.with_opacity(0.15, "#0f172a"),  # More transparent
            blur=ft.Blur(25, 25, ft.BlurTileMode.MIRROR),  # Higher blur
            border_radius=ft.BorderRadius.only(top_left=20, top_right=20),
            expand=True,
        )

    # --- Page Management ---
    def set_page(self, page: ft.Page):
        self._page = page
        threading.Thread(target=self._wait_until_added_and_load, daemon=True).start()

    def _ui(self, fn: Callable):
        """Execute a function on the UI thread."""
        if not self._page:
            return

        async def _coro():
            try:
                fn()
            except RuntimeError as e:
                if "added to the page first" not in str(e):
                    logger.debug(f"UI update error: {e}")
            except Exception as e:
                logger.debug(f"UI update error: {e}")

        self._page.run_task(_coro)

    # --- Add Dialog Toggling (Layer 1, isolated) ---
    def _show_add_dialog(self, e=None):
        """Show the add server/subscription modal (isolated Stack layer toggle)."""
        self.open_add_dialog()

    def open_add_dialog(self):
        """Open the in-page add modal — Layer 1 only, Layer 0 untouched."""
        self._add_modal.visible = True
        try:
            self._add_modal.update()
        except Exception:
            pass

    def _close_add_dialog(self):
        """Close the add modal — Layer 1 only, Layer 0 untouched."""
        self.close_add_dialog()

    def close_add_dialog(self):
        """Close the in-page add modal — Layer 1 only, Layer 0 untouched."""
        self._add_modal.visible = False
        try:
            self._add_modal.update()
        except Exception:
            pass
