"""Unit tests for NavigationController route state management and style token evaluation."""

from __future__ import annotations

from src.ui.controllers.navigation_controller import NavigationController


def test_navigation_controller_tab_switching():
    """Test tab switching and callback triggers."""
    changed_tabs = []

    def on_tab_changed(tab_id: str):
        changed_tabs.append(tab_id)

    ctrl = NavigationController(initial_tab="dashboard", on_tab_changed=on_tab_changed)
    assert ctrl.active_tab == "dashboard"

    ctrl.set_active_tab("servers")
    assert ctrl.active_tab == "servers"
    assert changed_tabs == ["servers"]

    ctrl.set_active_tab("settings")
    assert ctrl.active_tab == "settings"
    assert changed_tabs == ["servers", "settings"]


def test_navigation_controller_lan_style_tokens():
    """Test LAN button style tokens across LAN ON, active route, and inactive states."""
    ctrl = NavigationController(initial_tab="dashboard", allow_lan=False)

    # 1. Inactive & LAN OFF
    style_idle = ctrl.get_lan_button_style()
    assert style_idle.icon_color == "#c084fc"

    # 2. LAN ON
    ctrl.set_allow_lan(True)
    style_on = ctrl.get_lan_button_style()
    assert style_on.icon_color == "#4ADE80"

    # 3. Active LAN route but LAN OFF
    ctrl.set_allow_lan(False)
    ctrl.set_active_tab("lan")
    style_active = ctrl.get_lan_button_style()
    assert style_active.icon_color == "#8B5CF6"


def test_navigation_controller_quick_connect_style_tokens():
    """Test Quick Connect style tokens for running and disconnected states."""
    ctrl = NavigationController()

    # Disconnected state
    style_idle = ctrl.get_quick_connect_style(is_running=False)
    assert style_idle.icon_color == "#c084fc"
    assert style_idle.tooltip == "Quick Connect"

    # Running state
    style_running = ctrl.get_quick_connect_style(is_running=True)
    assert style_running.icon_color == "#f43f5e"
    assert style_running.tooltip == "Quick Disconnect"


def test_navigation_controller_nav_item_style_tokens():
    """Test nav item style tokens for active and inactive tabs."""
    ctrl = NavigationController(initial_tab="dashboard")

    # Active item (dashboard)
    style_active = ctrl.get_nav_item_style("dashboard")
    assert style_active.icon_color == "#c084fc"
    assert style_active.border is not None

    # Inactive item (servers)
    style_inactive = ctrl.get_nav_item_style("servers")
    assert style_inactive.border is None


def test_navigation_controller_sni_spoof_style_tokens():
    """Test SNI Spoof nav icon color is green (#4ADE80) when enabled, and default when disabled."""
    ctrl = NavigationController(initial_tab="dashboard", sni_spoof_enabled=False)

    # 1. Disabled and inactive: default muted color
    style_off = ctrl.get_nav_item_style("sni_spoof")
    assert style_off.icon_color != "#4ADE80"

    # 2. Enabled: green icon color (#4ADE80)
    ctrl.set_sni_spoof_enabled(True)
    style_on = ctrl.get_nav_item_style("sni_spoof")
    assert style_on.icon_color == "#4ADE80"

    # 3. Disabled again: returns to default color
    ctrl.set_sni_spoof_enabled(False)
    style_off_again = ctrl.get_nav_item_style("sni_spoof")
    assert style_off_again.icon_color != "#4ADE80"
