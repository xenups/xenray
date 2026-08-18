"""Tests for the component-driven SNI sections (Target/Relay/Card/Header)."""

import flet as ft

from src.ui.components.sni.sni_header import SniHeader
from src.ui.components.sni.sni_sections import SniRelaySection, SniSettingsCard, SniTargetSection


def _noop(*a, **k):
    return None


def test_sni_header_owns_chip_and_switch():
    header = SniHeader(is_rtl=False, enabled=True, on_toggle_change=_noop)
    assert header.master_switch.value is True
    # chip exposed both via property and internal
    assert hasattr(header, "status_chip")


def test_target_section_builds_fields():
    sec = SniTargetSection(
        fake_sni="chatgpt.com",
        connect_ip="185.193.30.94",
        connect_port="443",
        on_fake_sni_change=_noop,
        on_connect_ip_change=_noop,
        on_connect_port_change=_noop,
    )
    assert sec.fake_sni_field.value == "chatgpt.com"
    assert sec.connect_ip_field.value == "185.193.30.94"
    assert sec.connect_port_field.value == "443"


def test_relay_section_builds_fields():
    sec = SniRelaySection(
        listen_host="127.0.0.1",
        listen_port="40443",
        on_listen_host_change=_noop,
        on_listen_port_change=_noop,
    )
    assert sec.listen_host_field.value == "127.0.0.1"
    assert sec.listen_port_field.value == "40443"


def test_settings_card_contains_both_sections():
    target = SniTargetSection(
        fake_sni="a.com",
        connect_ip="1.2.3.4",
        connect_port="443",
        on_fake_sni_change=_noop,
        on_connect_ip_change=_noop,
        on_connect_port_change=_noop,
    )
    relay = SniRelaySection(
        listen_host="127.0.0.1",
        listen_port="40443",
        on_listen_host_change=_noop,
        on_listen_port_change=_noop,
    )
    card = SniSettingsCard(target_section=target, relay_section=relay)
    # card is a Container whose content is a Column (target, divider, relay)
    assert isinstance(card.content, ft.Column)
    # 3 children: target section, divider container, relay section
    assert len(card.content.controls) == 3
