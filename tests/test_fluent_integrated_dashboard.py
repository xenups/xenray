"""Unit tests for Fluent Integrated Dashboard UI components."""

from unittest.mock import MagicMock
import flet as ft
from src.ui.components.connection_button import ConnectionButton
from src.ui.components.nav_sidebar import NavSidebar
from src.ui.views.dashboard_view import DashboardView


def test_nav_sidebar_actions_panel():
    on_tab_change = MagicMock()
    on_connect_click = MagicMock()
    on_change_server_click = MagicMock()

    sidebar = NavSidebar(
        active_tab="dashboard",
        on_tab_change=on_tab_change,
        on_connect_click=on_connect_click,
        on_change_server_click=on_change_server_click,
    )

    assert sidebar._active_tab == "dashboard"
    assert sidebar._change_server_btn is not None
    assert sidebar._quick_action_btn is not None

    # Test update_connect_button_text when running
    sidebar.update_connect_button_text("Disconnect", is_running=True)
    assert sidebar._quick_action_text.value == "Quick Disconnect"

    # Test update_connect_button_text when disconnected
    sidebar.update_connect_button_text("Connect Now", is_running=False)
    assert sidebar._quick_action_text.value == "Quick Connect"


def test_connection_button_glassmorphism():
    on_click = MagicMock()
    btn = ConnectionButton(on_click=on_click)

    # Test initial state
    assert btn._state == "disconnected"

    # Test set_connected
    btn.set_connected()
    assert btn._state == "connected"

    # Test set_connecting
    btn.set_connecting()
    assert btn._state == "connecting"

    # Test set_disconnecting
    btn.set_disconnecting()
    assert btn._state == "disconnecting"

    # Test set_disconnected
    btn.set_disconnected()
    assert btn._state == "disconnected"


def test_dashboard_view_fluent_integrated():
    on_toggle = MagicMock()
    on_change_server = MagicMock()

    view = DashboardView(
        on_toggle_click=on_toggle,
        on_change_server_click=on_change_server,
    )

    # Verify server info update
    view.update_server_info(name="BunkerBuster", country_code="FI")
    assert "BunkerBuster (FI)" in view._server_name_text.value
    assert "https://flagcdn.com/w40/fi.png" in view._flag_img.src

    # Verify network stats update
    view.update_network_stats(
        rate_str="12.5 MB/s",
        upload_bps=6.3 * 1024 * 1024,
        total_bps=18.8 * 1024 * 1024,
    )
    assert "D: 12.5 MB/s" in view._dl_value_text.value
    assert "U: 6.3 MB/s" in view._ul_value_text.value

    # Verify connection state and status text underneath
    view.set_connection_state(is_connected=True)
    assert view._is_connected is True
    assert view._center_status_text.value == "Connected"

    # Verify uptime update underneath
    view.update_uptime("00:04:51")
    assert view._uptime_text.value == "00:04:51"
