"""Comprehensive unit and integration tests freezing UI views, component states, and services before refactoring."""

from __future__ import annotations

from unittest.mock import patch

import flet as ft

from src.core.i18n import set_language, t
from src.ui.components.common.nav_sidebar import NavSidebar
from src.ui.components.common.toast import ToastManager
from src.ui.pages.lan_sharing_page import LanSharingView, generate_qr_base64, get_real_physical_lan_ip
from src.ui.pages.logs_page import LogsView


def test_lan_physical_ip_detection():
    """Test that get_real_physical_lan_ip excludes 10.0.0.1 (TUN) and loopback."""
    ip = get_real_physical_lan_ip()
    assert ip != "10.0.0.1", "10.0.0.1 (TUN adapter) was not filtered out"
    assert not ip.startswith("127."), "Loopback IP was not filtered out"
    assert ip.startswith("192.168.") or ip.startswith("172.") or ip.startswith("10.")


def test_qr_base64_generation():
    """Test QR code generation produces valid PNG base64 data."""
    qr_str = generate_qr_base64("http://192.168.1.100:10809")
    assert qr_str is not None
    assert len(qr_str) > 50


@patch("src.utils.firewall_manager.FirewallManager.remove_lan_firewall_rule")
@patch("src.utils.firewall_manager.FirewallManager.add_lan_firewall_rule")
def test_lan_sharing_view_layout_and_toggle(mock_add, mock_remove):
    """Test LanSharingView structure and real-time toggle update."""

    class MockSettings:
        def __init__(self):
            self.allow = True

        def get_http_port(self):
            return 10809

        def get_proxy_port(self):
            return 10808

        def get_allow_lan(self):
            return self.allow

        def set_allow_lan(self, val):
            self.allow = val

    class MockAppContext:
        settings = MockSettings()

    app_ctx = MockAppContext()
    toggled = []

    view = LanSharingView(
        app_context=app_ctx,
        on_lan_toggle=lambda val: toggled.append(val),
    )

    assert view.content is not None
    assert view.allow_lan is True
    assert view._qr_card.is_qr_shown

    # Simulate toggle OFF
    event = type("E", (), {"control": type("C", (), {"value": False})()})()
    view._on_toggle_change(event)

    assert app_ctx.settings.get_allow_lan() is False
    assert view.allow_lan is False
    assert not view._qr_card.is_qr_shown
    assert toggled == [False]

    # Simulate toggle ON
    event.control.value = True
    view._on_toggle_change(event)

    assert app_ctx.settings.get_allow_lan() is True
    assert view.allow_lan is True
    assert view._qr_card.is_qr_shown
    assert toggled == [False, True]


def test_logs_view_metric_cards_flex_layout():
    """Test LogsView metric cards flex layout and updates."""
    log_ctrl = ft.ListView(expand=True)
    view = LogsView(
        log_text_control=log_ctrl,
        on_copy_logs_click=lambda: None,
        on_clear_logs_click=lambda: None,
    )

    assert view.content is not None
    top_metrics_row = view.content.controls[0]
    assert isinstance(top_metrics_row, ft.Row)
    assert len(top_metrics_row.controls) == 3

    m_card, t_card, h_card = top_metrics_row.controls
    assert m_card.expand == 1 and t_card.expand == 1 and h_card.expand == 1
    assert m_card.height == 110 and t_card.height == 110 and h_card.height == 110
    assert m_card.padding == 14 and t_card.padding == 14 and h_card.padding == 14

    # Test update methods without page reference
    view.update_memory(256.0, 1024.0)
    view.update_threads(8, "Optimal")
    view.update_health(0, "Healthy")


def test_nav_sidebar_lan_button_styling():
    """Test NavSidebar LAN button styling logic."""
    sb_off = NavSidebar(
        active_tab="dashboard",
        on_tab_change=lambda t: None,
        on_connect_click=lambda: None,
        allow_lan=False,
    )
    assert sb_off._lan_icon.color == "#c084fc"
    assert sb_off._lan_btn.border.top.color == "#a855f7,0.3"

    sb_on = NavSidebar(
        active_tab="dashboard",
        on_tab_change=lambda t: None,
        on_connect_click=lambda: None,
        allow_lan=True,
    )
    assert sb_on._lan_icon.color == "#4ADE80"
    assert sb_on._lan_btn.bgcolor == ft.Colors.with_opacity(0.15, "#10B981")

    sb_on.set_active_tab("lan")
    assert sb_on._lan_btn.border.top.color == "#8B5CF6"


def test_toast_manager_top_center_positioning():
    """Test ToastManager top-center container position (persistent overlay layer)."""

    class MockPage:
        def __init__(self):
            self.overlay = []

        def update(self, *controls):
            pass

        def run_task(self, *args, **kwargs):
            pass

    page = MockPage()
    tm = ToastManager(page)

    # A persistent top-center layer is mounted on the overlay.
    assert len(page.overlay) == 1
    layer = page.overlay[0]
    assert layer.alignment == ft.Alignment.TOP_CENTER

    # The toast container is appended INTO the layer at top=20, top-center.
    tm.show("Test message", "info", 3000)
    assert len(layer.controls) == 1
    container = layer.controls[0]
    assert container.top == 20
    assert container.alignment == ft.Alignment.TOP_CENTER


def test_i18n_status_phrases_fa_and_en():
    """Test i18n connection & status keys in Persian and English."""
    set_language("fa")
    assert t("app.connected") == "متصل"
    assert t("app.connecting") == "در حال اوج‌گیری"
    assert t("connection.verifying_latency") == "چک رادار"
    assert t("connection.initializing_vpn") == "آماده‌سازی باند"
    assert t("connection.starting_xray") == "روشن کردن موتور"

    set_language("en")
    assert t("app.connected") == "Connected"
    assert t("app.connecting") == "Revving up"
    assert t("connection.verifying_latency") == "Radar Check"
    assert t("connection.initializing_vpn") == "Preparing Runway"
    assert t("connection.starting_xray") == "Starting Engine"


def test_lan_service_failure_fallbacks(monkeypatch):
    """Test LanService handles network drops socket errors gracefully — and
    returns None (never a fabricated IP) when no OS source is reachable."""
    from src.services.system.lan_service import LanService

    def mock_socket(*args, **kwargs):
        raise OSError("No network sockets available")

    # Force the IP Helper source empty too.
    monkeypatch.setattr("src.platform.windows.network.get_physical_nic_candidates", lambda: [])
    monkeypatch.setattr("socket.socket", mock_socket)
    ip = LanService.get_real_physical_lan_ip()
    assert ip is None, f"Expected None (deterministic failure), got {ip}"

    # Invalid QR input
    assert LanService.generate_qr_base64(None) is None
