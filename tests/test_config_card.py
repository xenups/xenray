"""Unit tests for ConfigCard component and animated neon sweep gradient border trace."""

from __future__ import annotations

import asyncio
import math
from unittest.mock import MagicMock

import flet as ft
import pytest

from src.core.event_bus import TOPIC_SERVER_INSPECTED, TOPIC_SERVER_INSPECTING, event_bus
from src.ui.components.config.config_card import ConfigCard, ConfigListItem
from src.ui.components.servers.server_list_item import ServerListItem


@pytest.fixture
def sample_profile():
    return {
        "id": "srv-test-123",
        "name": "Neon Node 1",
        "country_code": "de",
        "config": {
            "outbounds": [
                {
                    "protocol": "vless",
                    "settings": {"vnext": [{"address": "1.2.3.4", "port": 443}]},
                }
            ]
        },
    }


def test_config_card_initialization(sample_profile):
    """Verify ConfigCard container hierarchy (outer 1.5px frame & inner solid dark card)."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)

    assert isinstance(card, ft.Container)
    assert card.padding.top == 1.5
    assert card.border_radius.top_left == 12
    assert card._inner_card.bgcolor == "#161922"
    assert card._inner_card.border_radius.top_left == 10.5
    assert issubclass(ServerListItem, ConfigCard)
    assert ConfigListItem is ConfigCard


@pytest.mark.asyncio
async def test_native_animation_properties_configured(sample_profile):
    """Verify the border disc uses Flet's GPU-accelerated rotate animation."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)
    disc = card._border_container

    # The rotating disc is a dedicated layer (not the card itself), positioned
    # so it never affects the Stack size.
    assert disc is not card
    assert disc.width == disc.height
    assert disc.gradient is None

    # The disc mounts with the 0.0 rotation anchor AND the GPU animation already
    # attached, so Flutter can interpolate the first target change immediately.
    assert disc.animate_rotation is not None
    assert disc.animate_rotation.duration == 1500
    assert disc.animate_rotation.curve == ft.AnimationCurve.LINEAR

    card.start_inspection_animation()
    assert disc.rotate.angle == pytest.approx(0.0)
    card.did_mount()
    await asyncio.sleep(0.1)
    assert disc.rotate.angle == pytest.approx(2 * math.pi)
    card.will_unmount()


def test_card_size_change_sizes_disc_to_diagonal(sample_profile):
    """Verify on_size_change sizes the disc to the card's diagonal (no corner clipping)."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)

    class _SizeEvent:
        width = 280.0
        height = 65.0

    card._on_card_size_changed(_SizeEvent())
    expected = math.hypot(280.0, 65.0)
    assert card._border_container.width == pytest.approx(expected)
    assert card._border_container.height == pytest.approx(expected)
    card.will_unmount()


def test_inspection_animation_start_stop(sample_profile):
    """Verify start_inspection_animation and stop_inspection_animation toggle SweepGradient."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)

    # Initial state — static border
    assert card._is_inspecting is False
    assert card._border_container.gradient is None
    assert card.border is not None

    # Start animation
    card.start_inspection_animation()
    assert card._is_inspecting is True
    assert card._border_container.gradient is card._sweep_gradient
    assert card.border is None

    # Stop animation
    card.stop_inspection_animation()
    assert card._is_inspecting is False
    assert card._border_container.gradient is None
    assert card.border is not None


@pytest.mark.asyncio
async def test_inspection_sweep_rotation_loop(sample_profile):
    """Verify async rotation loop advances the disc rotation."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)
    initial_rotation = card._border_container.rotate.angle

    card.start_inspection_animation()
    card.did_mount()  # simulate mount -> schedule the animation coroutine
    await asyncio.sleep(0.1)

    assert card._border_container.rotate.angle != initial_rotation
    card.stop_inspection_animation()


@pytest.mark.asyncio
async def test_native_rotation_nudges_full_turn(sample_profile):
    """Verify the frame-flush + loop nudges advance by full 360° turns."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)
    disc = card._border_container

    # Construction: rotation anchor (0.0) + GPU animation attached and ready.
    assert disc.rotate.angle == pytest.approx(0.0)
    assert disc.animate_rotation is not None

    card.start_inspection_animation()

    # The target is NOT applied synchronously — the disc still holds the 0.0
    # anchor so it is never rendered directly at the animation target.
    assert disc.rotate.angle == pytest.approx(0.0)

    # Mount schedules the coroutine, which (after a frame flush) targets the
    # first full turn in a separate client frame so the native 0 -> 2π
    # transition interpolates.
    card.did_mount()
    await asyncio.sleep(0.1)
    assert disc.rotate.angle == pytest.approx(2 * math.pi)

    card.stop_inspection_animation()

    # After stopping, the disc is reset to the anchor and the static border returns.
    assert disc.rotate.angle == pytest.approx(0.0)
    assert disc.animate_rotation is not None  # kept ready for the next inspection
    assert disc.gradient is None
    card.will_unmount()


def test_frame_boundary_before_native_target(sample_profile):
    """Verify the first rotation target is applied by the coroutine (after a frame
    flush), never synchronously in the same pass as the anchor/mount."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)
    disc = card._border_container
    assert disc.rotate.angle == 0.0
    assert disc.animate_rotation is not None

    card.start_inspection_animation()

    # Still on the anchor (unmounted) — the target is NOT applied yet.
    assert disc.rotate.angle == pytest.approx(0.0)

    # Mount only SCHEDULES the coroutine (which runs later, after the frame
    # flush); it must not set the target synchronously.
    card.did_mount()
    assert disc.rotate.angle == pytest.approx(0.0)
    card.will_unmount()


def test_inspection_completion_updates_card(sample_profile):
    """stop_inspection_animation + update_ping update the card's badge in place."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)
    card.start_inspection_animation()
    assert card._is_inspecting is True

    card.stop_inspection_animation()
    card.update_ping("42ms", ft.Colors.GREEN_400)

    assert card._is_inspecting is False
    assert "42" in card.latency_text.value
    card.will_unmount()


def test_start_inspection_animation_starts_sweep(sample_profile):
    """Verify the card's public start_inspection_animation starts the sweep."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)
    assert card._is_inspecting is False
    assert card._border_container.gradient is None

    card.start_inspection_animation()

    assert card._is_inspecting is True
    assert card._border_container.gradient is card._sweep_gradient
    assert card.border is None
    card.will_unmount()


def test_ping_badge_click_triggers_shared_inspection_pipeline(sample_profile):
    """Clicking the card's ping badge must route through the shared
    server_inspector pipeline (non-blocking + throttled)."""
    from unittest.mock import patch

    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)
    assert hasattr(card, "ping_badge") and card.ping_badge is not None
    assert card.ping_badge.content is card.latency_text

    with patch("src.services.server_inspector.server_inspector.inspect") as mock_inspect:
        card._on_ping_click()
    mock_inspect.assert_called_once_with(card._profile)
    card.will_unmount()


def test_server_list_delegates_inspection_events_to_cards():
    """ServerList is the SINGLE EventBus subscriber; events start/stop the
    specific card via _item_map — cards never subscribe individually."""
    from unittest.mock import MagicMock

    from src.ui.components.servers.server_list import ServerList

    ctx = MagicMock()
    ctx.settings.get_sort_mode.return_value = None
    ctx.settings.get_last_selected_profile_id.return_value = None
    ctx.profiles.load_all.return_value = []
    ctx.subscriptions.load_all.return_value = []
    ctx.load_chains.return_value = []
    sl = ServerList(app_context=ctx, on_server_selected=lambda p: None)
    sl._load_profiles(update_ui=False)
    sl._ui = lambda fn: fn()  # run UI callbacks synchronously in the test

    sl.append_server_item({"id": "p1", "name": "A", "config": {}})
    card = sl._item_map["p1"]
    assert card._is_inspecting is False

    # Inspection begins -> ServerList starts ONLY that card's sweep.
    event_bus.publish(TOPIC_SERVER_INSPECTING, {"server_id": "p1"})
    assert "p1" in sl._inspecting_ids
    assert card._is_inspecting is True

    # Inspection completes -> ServerList stops the sweep + updates the badge.
    event_bus.publish(
        TOPIC_SERVER_INSPECTED,
        {"server_id": "p1", "success": True, "ping": 42, "result_str": "42ms"},
    )
    assert card._is_inspecting is False
    assert "42" in card.latency_text.value


def test_constructor_is_inspecting_flag_starts_animation(sample_profile):
    """Verify an explicit is_inspecting flag starts the animation immediately."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None, is_inspecting=True)
    assert card._is_inspecting is True
    assert card._border_container.gradient is card._sweep_gradient
    assert card.border is None

    card.stop_inspection_animation()
    assert card._is_inspecting is False
    assert card._border_container.gradient is None
    card.will_unmount()


def test_constructor_profile_hint_starts_animation(sample_profile):
    """Verify a profile carrying is_inspecting=True also starts the animation."""
    profile = {**sample_profile, "is_inspecting": True}
    card = ConfigCard(profile=profile, on_select=lambda p: None)
    assert card._is_inspecting is True
    assert card._border_container.gradient is card._sweep_gradient
    card.will_unmount()


@pytest.mark.asyncio
async def test_start_inspection_animation_drives_rotation_loop(sample_profile):
    """Verify start_inspection_animation drives the native rotation loop."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)
    initial_rotation = card._border_container.rotate.angle

    card.start_inspection_animation()
    card.did_mount()  # simulate mount -> schedule the animation coroutine
    await asyncio.sleep(0.1)

    assert card._border_container.rotate.angle != initial_rotation
    card.stop_inspection_animation()
    card.will_unmount()


class _FakePage:
    """Minimal page stub exposing the run_task contract used by ConfigCard."""

    def __init__(self, loop):
        self._loop = loop

    def run_task(self, handler, *args, **kwargs):
        return asyncio.run_coroutine_threadsafe(handler(*args, **kwargs), self._loop)


@pytest.mark.asyncio
async def test_start_animation_schedules_via_page_loop(sample_profile, monkeypatch):
    """Verify a mounted card schedules the sweep loop through the page event loop."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)
    page = _FakePage(asyncio.get_running_loop())
    monkeypatch.setattr(card, "_safe_page", lambda: page)

    initial_rotation = card._border_container.rotate.angle
    card.start_inspection_animation()

    # Simulate the Flet did_mount() hook firing after attachment.
    card.did_mount()
    await asyncio.sleep(0.1)

    assert card._is_inspecting is True
    assert card._border_container.rotate.angle != initial_rotation
    card.stop_inspection_animation()
    card.will_unmount()


def test_unmount_cleanup(sample_profile):
    """Verify will_unmount unsubscribes from EventBus and cancels task."""
    card = ConfigCard(profile=sample_profile, on_select=lambda p: None)
    card.start_inspection_animation()

    card.will_unmount()
    assert card._is_inspecting is False
    assert card._inspect_task is None
