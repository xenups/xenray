"""Tests for the first-ping animation race and sort-preserves-latency fixes."""

from __future__ import annotations

import types

from src.ui.components.config.config_card import ConfigCard


class _FakePage:
    """Minimal page stub: run_task collects coroutines instead of executing them."""

    def __init__(self):
        self.tasks = []

    def run_task(self, coro):
        self.tasks.append(coro)
        return None


def _build_card(page, is_inspecting: bool = False, pending_start: bool = False):
    """Construct a ConfigCard and simulate the mount race."""
    profile = {
        "id": "srv-1",
        "name": "Test Server",
        "address": "example.com",
        "config": {"outbounds": [{"protocol": "vmess", "settings": {"vnext": [{"address": "example.com"}]}}]},
    }
    card = ConfigCard(
        profile=profile,
        on_select=lambda p: None,
        on_delete=None,
        is_selected=False,
        read_only=True,
        cached_ping=None,
        is_inspecting=is_inspecting,
    )
    # Simulate a card built on a background thread (no page yet)
    if pending_start:
        card._pending_start = True
        card._is_inspecting = False  # inspection completed before mount
    # Mount it: Flet calls did_mount when attached to the page. _safe_page()
    # returns card.page which is None until the control is added to the tree,
    # so we stub it to simulate a successfully attached card.
    card._safe_page = lambda: page
    card._schedule_animation = lambda: page.tasks.append("sweep") or None
    card.did_mount()
    return card


def test_first_ping_animation_starts_after_mount_race():
    """The first ping's sweep must start even if the inspection finished before mount.

    Regression: did_mount used to require _is_inspecting AND _pending_start;
    when the inspection completed before the card mounted, _is_inspecting was
    False and the sweep never rendered — the FIRST ping showed no animation.
    """
    page = _FakePage()
    card = _build_card(page, is_inspecting=False, pending_start=True)

    # did_mount should have re-entered start_inspection_animation() now that the
    # card is attached -> _safe_page() resolves -> a sweep task is scheduled.
    assert card._is_inspecting is True, "sweep should be running after mount"
    assert page.tasks, "an animation task should have been scheduled"


def test_pending_start_cleared_after_mount():
    page = _FakePage()
    card = _build_card(page, is_inspecting=False, pending_start=True)
    assert card._pending_start is False, "_pending_start must be consumed by did_mount"


def test_mount_without_pending_start_is_noop():
    page = _FakePage()
    card = _build_card(page, is_inspecting=False, pending_start=False)
    assert card._is_inspecting is False
    assert page.tasks == []


def test_sort_reapplies_latency_badge():
    """_resort_profiles_in_place must re-apply ping values after reordering.

    Regression: reordering ListView controls can re-mount children on the
    client, rebuilding the card from construction-time cached_ping (None) and
    showing "..." even though the in-memory model has fresh latency.
    """
    from src.ui.components.servers.server_list_item import ServerListItem
    from src.ui.components.servers.server_list_sort import ServerListSortMixin

    class FakeList(ServerListSortMixin):
        def __init__(self):
            self._profiles = []
            self._current_list_view = None
            self._latency_tester = types.SimpleNamespace(get_cached_result=lambda pid: None)
            self._app_context = types.SimpleNamespace(settings=types.SimpleNamespace(get_sort_mode=lambda: "ping_asc"))

    fl = FakeList()
    fl._profiles = [
        {"id": "b", "name": "B", "last_latency_val": 456, "config": {"outbounds": [{"protocol": "vmess"}]}},
        {"id": "a", "name": "A", "last_latency_val": 123, "config": {"outbounds": [{"protocol": "vmess"}]}},
    ]

    # Build two cards exactly as the loader does (cached_ping=None => "..." initially)
    cards = []
    for p in fl._profiles:
        card = ServerListItem(
            profile=p,
            on_select=lambda p: None,
            cached_ping=None,
            read_only=True,
        )
        cards.append(card)

    list_view = types.SimpleNamespace(controls=cards[:], update=lambda: None)
    fl._current_list_view = list_view

    # Re-sort (ping_asc => A first)
    fl._resort_profiles_in_place()

    order = [c._profile["id"] for c in fl._current_list_view.controls]
    assert order == ["a", "b"], f"cards should be sorted by latency, got {order}"
    # The latency badge must now show the real value, not "..."
    for card in fl._current_list_view.controls:
        pid = card._profile["id"]
        expected = "123" if pid == "a" else "456"
        assert (
            expected in card.latency_text.value
        ), f"card {pid} should show {expected}, got {card.latency_text.value!r}"
