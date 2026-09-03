"""Unit tests for incremental DOM updates in ServerList (append, in-place select, partial delete)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import flet as ft
import pytest

from src.ui.components.servers.server_list import ServerList
from src.ui.components.servers.server_list_item import ServerListItem


@pytest.fixture
def mock_app_context():
    class MockSettings:
        def get_sort_mode(self):
            return "default"

        def set_sort_mode(self, mode):
            pass

        def get_last_selected_profile_id(self):
            return None

    class MockProfiles:
        def __init__(self):
            self.data = {}

        def load_all(self):
            return list(self.data.values())

        def get(self, pid):
            return self.data.get(pid)

        def save(self, name, config):
            pid = f"srv-{len(self.data) + 1}"
            prof = {"id": pid, "name": name, "config": config}
            self.data[pid] = prof
            return pid

        def delete(self, pid):
            self.data.pop(pid, None)

    class MockSubscriptions:
        def load_all(self):
            return []

    ctx = MagicMock()
    ctx.settings = MockSettings()
    ctx.profiles = MockProfiles()
    ctx.subscriptions = MockSubscriptions()
    ctx.load_chains.return_value = []
    return ctx


def test_incremental_append_server_item(mock_app_context):
    """Verify append_server_item inserts directly at ListView.controls[0] without a full re-render."""
    sl = ServerList(app_context=mock_app_context, on_server_selected=lambda p: None)

    # Initial load
    sl._load_profiles(update_ui=False)
    initial_list_view = sl._current_list_view
    assert initial_list_view is not None

    new_prof = {"id": "srv-new-99", "name": "New Server Node", "config": {}}
    appended_item = sl.append_server_item(new_prof)

    # Verify same ListView instance is preserved
    assert sl._current_list_view is initial_list_view
    assert appended_item in initial_list_view.controls
    assert sl._item_map.get("srv-new-99") is appended_item
    assert isinstance(appended_item, ServerListItem)

    # The new card must appear at the VERY TOP (index 0) of the list
    assert initial_list_view.controls[0] is appended_item
    assert sl._profiles[0]["id"] == "srv-new-99"


@pytest.mark.asyncio
async def test_chunked_append_builds_all_cards(mock_app_context):
    """Large lists render progressively: an initial batch + chunked appends must
    eventually contain every card (no all-at-once dataclass build)."""

    class FakePage:
        def run_task(self, coro, *a, **k):
            return asyncio.get_running_loop().create_task(coro(*a, **k))

    sl = ServerList(app_context=mock_app_context, on_server_selected=lambda p: None)
    sl._page = FakePage()

    profiles = [{"id": f"s{i}", "name": f"S{i}", "config": {}} for i in range(100)]
    lv = ft.ListView()
    sl._current_list_view = lv

    # First RENDER_CHUNK injected instantly (as _load_profiles does).
    for p in profiles[: sl.RENDER_CHUNK]:
        item = sl._create_server_item(p)
        lv.controls.append(item)
        sl._item_map[p["id"]] = item

    # Remaining cards appended in micro-chunks on the page loop.
    sl._schedule_chunked_append(lv, profiles[sl.RENDER_CHUNK :])
    await asyncio.sleep(0.3)

    assert len(lv.controls) == 100
    assert len(sl._item_map) == 100


def test_header_ping_button_toggles_stop(mock_app_context):
    """The Ping All button must toggle to 'Stop Ping' and back (in-place)."""
    import flet as ft

    from src.ui.components.servers.server_list_header import ServerListHeader

    header = ServerListHeader(
        get_sort_mode=lambda: None,
        set_sort_mode=lambda m: None,
        on_test_latency=lambda: None,
        on_add_click=lambda: None,
        on_cancel_ping=lambda: None,
    )

    assert header._ping_all_btn is not None
    assert header._ping_all_btn.icon == ft.Icons.SPEED

    header.set_ping_state(True)
    assert header._ping_active is True
    assert header._ping_all_btn.icon == ft.Icons.STOP_ROUNDED

    header.set_ping_state(False)
    assert header._ping_active is False
    assert header._ping_all_btn.icon == ft.Icons.SPEED


def test_search_matches_country_name_code_and_localized(mock_app_context):
    """Search must match country name, code, address, AND the localized name."""
    from src.core.i18n import set_language

    sl = ServerList(app_context=mock_app_context, on_server_selected=lambda p: None)
    finland = {
        "id": "p1",
        "name": "Helsinki Relay",
        "address": "fi-node.example.com",
        "country_code": "fi",
        "country_name": "Finland",
        "config": {
            "outbounds": [
                {
                    "protocol": "vless",
                    "settings": {"vnext": [{"address": "1.2.3.4", "port": 443}]},
                }
            ]
        },
    }
    uk = {
        "id": "p2",
        "name": "London",
        "country_code": "gb",
        "country_name": "United Kingdom",
        "config": {"outbounds": []},
    }

    for q in ["finland", "FI", "fi", "helsinki", "fi-node", "1.2.3.4"]:
        sl._search_query = q.lower()
        assert sl._matches_query(finland), f"'{q}' must match Finland"
        assert not sl._matches_query(uk), f"'{q}' must not match UK"

    # Localized country name (Persian)
    set_language("fa")
    try:
        sl._localized_country_cache.clear()
        sl._search_query = "فنلاند"
        assert sl._matches_query(finland), "'فنلاند' must match the FI server"
        assert not sl._matches_query(uk)
    finally:
        set_language("en")


def test_handle_server_added_appends_in_place(mock_app_context):
    """Verify adding a server inserts the card at the TOP (no full list rebuild/flicker)."""
    sl = ServerList(app_context=mock_app_context, on_server_selected=lambda p: None)
    sl._load_profiles(update_ui=False)
    initial_list_view = sl._current_list_view

    # Mock the ping queue so inspect() publishes the inspecting event but no real
    # network ping is queued (the submission-time publish drives the neon sweep).
    with patch("src.services.connection.server_inspector.ping_manager.submit"):
        sl._handle_server_added("New Server", {"outbounds": []})

    # Same ListView instance is preserved (no AnimatedSwitcher content swap).
    assert sl._current_list_view is initial_list_view

    # The new card is inserted at index 0 (top of the list) and tracked.
    cards = [c for c in initial_list_view.controls if isinstance(c, ServerListItem)]
    new_cards = [c for c in cards if c._profile.get("name") == "New Server"]
    assert len(new_cards) == 1
    assert sl._item_map.get(new_cards[0]._profile.get("id")) is new_cards[0]
    assert initial_list_view.controls[0] is new_cards[0]

    # The card is marked inspecting (start_inspection_animation runs at mount).
    assert new_cards[0]._is_inspecting is True


def test_incremental_select_server(mock_app_context):
    """Verify _select_server updates item borders in-place without triggering full list reload."""
    p1 = {"id": "p1", "name": "Node 1", "config": {}}
    p2 = {"id": "p2", "name": "Node 2", "config": {}}
    mock_app_context.profiles.data = {"p1": p1, "p2": p2}

    sl = ServerList(app_context=mock_app_context, on_server_selected=lambda p: None)
    sl._load_profiles(update_ui=False)
    initial_list_view = sl._current_list_view

    item1 = sl._item_map["p1"]
    item2 = sl._item_map["p2"]

    # Select p1
    sl._select_server(p1)
    assert sl._selected_profile_id == "p1"
    assert item1._is_selected is True
    assert item2._is_selected is False
    assert sl._current_list_view is initial_list_view

    # Select p2
    sl._select_server(p2)
    assert sl._selected_profile_id == "p2"
    assert item1._is_selected is False
    assert item2._is_selected is True
    assert sl._current_list_view is initial_list_view


def test_incremental_delete_server(mock_app_context):
    """Verify _delete_server removes item directly from ListView.controls without full list reload."""
    p1 = {"id": "p1", "name": "Node 1", "config": {}}
    mock_app_context.profiles.data = {"p1": p1}

    sl = ServerList(app_context=mock_app_context, on_server_selected=lambda p: None)
    sl._load_profiles(update_ui=False)
    initial_list_view = sl._current_list_view

    item1 = sl._item_map["p1"]
    assert item1 in initial_list_view.controls

    # Delete p1
    sl._delete_server("p1")
    assert item1 not in initial_list_view.controls
    assert "p1" not in sl._item_map
    assert sl._current_list_view is initial_list_view


def test_inspect_result_persists_ping(mock_app_context):
    """_on_server_inspected must persist the resolved ping (not just keep it
    in-memory) so it survives a restart (read back from the repo on load)."""
    from src.ui.components.servers.server_list import ServerList

    # Give the mock repo an update() + get_by_id() so the persist path runs.
    persisted = {}

    def fake_get_by_id(pid):
        return persisted.get(pid) or {"id": pid}

    def fake_update(pid, updates):
        persisted.setdefault(pid, {"id": pid}).update(updates)
        return True

    mock_app_context.profiles.get_by_id = fake_get_by_id
    mock_app_context.profiles.update = fake_update

    sl = ServerList(app_context=mock_app_context, on_server_selected=lambda p: None)

    # A profile already in the list
    prof = {"id": "srv-persist-1", "name": "Srv"}
    sl._profiles = [prof]
    sl._item_map = {}

    sl._on_server_inspected(
        {
            "server_id": "srv-persist-1",
            "success": True,
            "ping": 123,
            "result_str": "Latency: 123 ms",
            "location": {},
        }
    )

    assert persisted["srv-persist-1"]["last_latency_val"] == 123
    assert persisted["srv-persist-1"]["last_latency"] == "Latency: 123 ms"
