"""Tests for the Statistics page: NO empty-state overlay (removed per user
request) — the page shows the cards with "—" placeholders until the first
real telemetry payload populates them with values."""

from __future__ import annotations

import flet as ft

from src.ui.pages.statistics_page import StatisticsPage


def _make_page() -> StatisticsPage:
    page = StatisticsPage()
    try:
        # Mount the page so controls can be read/updated (detached controls
        # return None for `page`); the test stays fully offline otherwise.
        page._page = ft.Page()
    except Exception:
        pass
    return page


def test_no_empty_state_overlay() -> None:
    """The empty-state overlay must NOT exist (user removed it)."""
    page = _make_page()
    assert not hasattr(page, "_empty_state")


def test_initial_state_uses_placeholder_dashes() -> None:
    """Initially (no data) the value controls hold '—', never fake zeros."""
    page = _make_page()
    assert page._has_data is False
    assert page._dl_speed_text.value == "—"
    assert page._ul_speed_text.value == "—"
    assert page._total_transfer_text.value == "—"
    assert "0.0" not in page._dl_speed_text.value


def test_first_telemetry_populates_values() -> None:
    """The first real telemetry payload fills the cards with real values."""
    page = _make_page()
    page._is_connected = True
    page.set_visible(True)

    page.update_network_stats(
        rate_str="1.2 MB/s",
        download_bps=1_200_000,
        upload_bps=300_000,
        total_bps=1_500_000,
        upload_total="5.0 MB",
        download_total="12.0 MB",
        _has_data=True,
    )

    assert page._has_data is True
    assert page._dl_speed_text.value != "—"


def test_synthetic_zero_payload_does_not_count() -> None:
    """All-zero synthetic payloads never flip _has_data (no fake zeros)."""
    page = _make_page()
    page._is_connected = True

    page.update_network_stats(download_bps=0.0, upload_bps=0.0, total_bps=0.0, _has_data=False)

    assert page._has_data is False


def test_disconnect_resets_to_placeholders() -> None:
    """Disconnecting after data was shown resets values to '—'."""
    page = _make_page()
    page._is_connected = True
    page.update_network_stats(download_bps=1_000_000, _has_data=True)
    assert page._has_data is True

    page.set_connection_state(is_connected=False)

    assert page._has_data is False
    assert page._dl_speed_text.value == "—"


def test_cached_telemetry_rendered_immediately_on_set_visible() -> None:
    """Telemetry cached while hidden renders instantly when page becomes visible."""
    page = _make_page()
    page._is_connected = True
    page._is_visible = False

    # Telemetry arrives while on another tab
    page.update_network_stats(
        rate_str="3.5 MB/s",
        download_bps=3_500_000,
        upload_bps=500_000,
        total_bps=4_000_000,
        upload_total="10.0 MB",
        download_total="50.0 MB",
        _has_data=True,
    )

    # Values in controls are still placeholders because page is hidden
    assert page._dl_speed_text.value == "—"
    assert page._last_payload is not None

    # User clicks on Statistics tab
    page.set_visible(True)

    # Values are now immediately populated with no delay or timer wait
    assert page._dl_speed_text.value != "—"
    assert page._rate_text_control.value == "3.5 MB/s"


def test_telemetry_event_syncs_is_connected() -> None:
    """EventBus telemetry payload with is_connected=True sets _is_connected and updates."""
    page = _make_page()
    page.set_visible(True)
    assert page._is_connected is False

    page._on_telemetry_event(
        {
            "is_connected": True,
            "rate_str": "2.0 MB/s",
            "download_bps": 2_000_000,
            "upload_bps": 1_000_000,
            "total_bps": 3_000_000,
            "download_total": "20.0 MB",
            "upload_total": "5.0 MB",
        }
    )

    assert page._is_connected is True
    assert page._has_data is True
    assert page._dl_speed_text.value != "—"
