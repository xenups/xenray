"""List mutation actions for the ServerList component (single-responsibility mixin)."""

from __future__ import annotations

from typing import Optional

from src.core.i18n import t
from src.core.logger import logger
from src.services.connection.server_inspector import server_inspector
from src.ui.components.servers.server_list_item import ServerListItem


class ServerListActionsMixin:
    """Mixin providing incremental list mutations — no state of its own."""

    def _select_server(self, profile: dict):
        """Handle server selection incrementally without full list re-render."""
        old_pid = str(self._selected_profile_id) if self._selected_profile_id else None
        new_pid = str(profile.get("id"))
        self._selected_profile_id = new_pid

        if self._on_server_selected:
            self._on_server_selected(profile)

        # Update previous selected item and new selected item borders without full list reload
        old_item = self._item_map.get(old_pid) if old_pid else None
        new_item = self._item_map.get(new_pid)

        if old_item:
            old_item._is_selected = False
            old_item._update_border_style()
            try:
                if old_item.page:
                    old_item.update()
            except Exception:
                pass

        if new_item:
            new_item._is_selected = True
            new_item._update_border_style()
            try:
                if new_item.page:
                    new_item.update()
            except Exception:
                pass

    def _delete_server(self, profile_id: str):
        """Delete a server profile incrementally without full list re-render."""
        self._app_context.profiles.delete(profile_id)
        pid_str = str(profile_id)
        self._profiles = [p for p in self._profiles if str(p.get("id")) != pid_str]
        item = self._item_map.pop(pid_str, None)

        if item and self._current_list_view and item in self._current_list_view.controls:
            self._current_list_view.controls.remove(item)
            try:
                if self._current_list_view.page is not None:
                    self._current_list_view.update()
            except Exception as ex:
                logger.debug(f"[ServerList] ListView remove update exception: {ex}")
        else:
            self._load_profiles(update_ui=True)

        if self._toast:
            self._toast.success(t("server_list.server_deleted"))

    def append_server_item(self, profile: dict) -> Optional[ServerListItem]:
        """Insert a single new server item at the TOP (index 0) of the ListView
        without a full re-render, so the user immediately sees the new card, its
        inspection state, and its neon animation."""
        pid = profile.get("id")
        if not pid:
            return None

        pid_str = str(pid)
        logger.debug(f"[ServerList] append_server_item for {pid_str}")
        # Avoid duplicate additions
        if pid_str in self._item_map:
            return self._item_map[pid_str]

        # Add profile to internal list if missing (newest first)
        if not any(str(p.get("id")) == pid_str for p in self._profiles):
            self._profiles.insert(0, profile)

        # Build single new item control
        cached = self._latency_tester.get_cached_result(pid_str)
        item = ServerListItem(
            profile=profile,
            on_select=self._select_server,
            on_delete=self._delete_server,
            is_selected=(self._selected_profile_id == pid_str),
            cached_ping=cached,
            is_inspecting=(pid_str in self._inspecting_ids or profile.get("status") == "inspecting"),
        )
        self._item_map[pid_str] = item

        # Insert directly at index 0 of ListView.controls if it exists
        if self._current_list_view is not None:
            self._current_list_view.controls.insert(0, item)
            try:
                if self._current_list_view.page is not None:
                    self._current_list_view.update()
            except Exception as ex:
                logger.debug(f"[ServerList] ListView insert update exception: {ex}")
        else:
            self._load_profiles(update_ui=True)

        return item

    def _handle_server_added(self, name: str, config: dict):
        """Handle a new server being added (auto-inspects in the background).

        Inserts the new card at the TOP (index 0) of the existing list in place
        instead of rebuilding the whole list/page tree. Rebuilding tears down
        every control and swaps the AnimatedSwitcher content, which causes page
        flicker and loses hover/click state on sidebar and add buttons.
        """
        pid = self._app_context.profiles.save(name, config)
        if not pid:
            return

        # Auto-ping + location detection for the imported server (background).
        server_inspector.inspect({"id": pid, "name": name, "config": config})

        # TODO: temporarily disabled to isolate a UI freeze/delay after adding a config.
        # if self._toast:
        #     self._toast.success(t("add_dialog.server_added", name=name))

        # Incremental append (no full re-render) when showing the main profile
        # list (no active subscription folder, no search filter active).
        profile = {"id": pid, "name": name, "config": config}
        if self._current_list_view is not None and self._active_subscription is None and not self._search_query:
            self.append_server_item(profile)
            return

        self._load_profiles(update_ui=True)

    def _handle_subscription_added(self, name: str, url: str):
        """Handle a new subscription being added (fetches + auto-inspects)."""
        sub_id = self._app_context.subscriptions.save(name, url)
        if sub_id:
            self._subscription_manager.update_subscription(sub_id, callback=None)
        self._load_profiles(update_ui=True)
