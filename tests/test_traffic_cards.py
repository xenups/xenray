"""Tests for the TrafficCards speed-card layout anchoring (icon jitter fix)."""

from __future__ import annotations

import flet as ft

from src.ui.components.dashboard.traffic_cards import TrafficCards


def _card(tc: TrafficCards, index: int) -> ft.Row:
    card = tc.controls[index]
    assert isinstance(card, ft.Container)
    assert isinstance(card.content, ft.Row)
    return card.content


def test_speed_cards_anchor_icon_left_with_expanding_text():
    tc = TrafficCards()

    for i in range(2):
        row = _card(tc, i)
        icon_box, text_col = row.controls[0], row.controls[1]

        # Strict fixed icon box anchored on the left with its own right margin.
        assert isinstance(icon_box, ft.Container)
        assert icon_box.width == 42
        assert icon_box.height == 42
        assert icon_box.margin.right in (10, 12)

        # Text column has fixed width so total row width is constant (0 icon jitter + centered card content).
        assert text_col.width == 105
        assert text_col.horizontal_alignment == ft.CrossAxisAlignment.START

        # Row is centered horizontally and vertically.
        assert row.alignment == ft.MainAxisAlignment.CENTER
        assert row.vertical_alignment == ft.CrossAxisAlignment.CENTER


def test_value_changes_do_not_shift_icon_layout():
    tc = TrafficCards()
    icon_box = _card(tc, 0).controls[0]

    before = (icon_box.width, icon_box.height, icon_box.margin.right)

    tc.update_speeds("0.0 B/s", "0.0 B/s")
    tc.update_speeds("125.4 MB/s", "8.3 KB/s")

    after = (icon_box.width, icon_box.height, icon_box.margin.right)
    assert before == after
    assert tc._dl_value_text.value == "125.4 MB/s"
    assert tc._ul_value_text.value == "8.3 KB/s"


def test_cards_are_clickable_with_cursor_hint():
    clicks = []
    tc = TrafficCards(on_card_click=lambda e: clicks.append(e))

    for card in tc.controls:
        assert isinstance(card, ft.Container)
        assert card.on_click is not None
        assert card.on_hover is not None

    # Simulate a click on each speed card.
    tc.controls[0].on_click("download")
    tc.controls[1].on_click("upload")
    assert clicks == ["download", "upload"]


def test_cards_always_show_hand_cursor():
    tc = TrafficCards()
    for card in tc.controls:
        assert isinstance(card, ft.Container)
        assert card.on_click is not None
        assert card.on_hover is not None


def test_network_stats_stop_flushes_cached_metrics():
    """Stopping the monitor must flush the cached buffer so get_stats() returns
    zeros after a disconnect (no stale last-recorded speeds)."""
    from src.services.monitoring.network_stats import NetworkStatsService

    svc = NetworkStatsService()
    svc._running = True
    svc._cached_stats = {
        "download_speed": "12 MB/s",
        "upload_speed": "3 MB/s",
        "total_bps": 100.0,
    }

    svc.stop()

    stats = svc.get_stats()
    assert stats["download_speed"] == "0 B/s"
    assert stats["upload_speed"] == "0 B/s"
    assert stats["total_bps"] == 0.0


def test_dashboard_resets_traffic_metrics_on_disconnect():
    """Reaching FSM DISCONNECTED must zero the Download/Upload badges in place."""
    from unittest.mock import MagicMock

    from src.ui.pages.dashboard_page import DashboardPage

    page = DashboardPage(
        on_toggle_click=lambda e: None,
        on_change_server_click=lambda e: None,
        on_open_statistics_click=lambda e: None,
    )
    fake_cards = MagicMock()
    page._traffic_cards = fake_cards

    page._apply_fsm_state_event({"new_state": "disconnected"})
    fake_cards.update_speeds.assert_called_with("0 B/s", "0 B/s")
    page.dispose()
