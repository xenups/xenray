"""Tests for ConnectionButton states and NeonSweepBorder.set_palette."""

from src.ui.components.dashboard.connection_button import ConnectionButton


def _button() -> ConnectionButton:
    btn = ConnectionButton(on_click=lambda e: None)
    btn._has_page_attached = lambda: False
    return btn


def test_connecting_state_styling():
    btn = _button()
    btn.set_connecting("Connecting")
    assert btn._is_connecting is True
    assert btn._is_connected is False
    assert btn._button.bgcolor == "#EDE9FE"
    assert btn._button.opacity == 1.0


def test_connected_state_styling():
    btn = _button()
    btn.set_connected("Connected")
    assert btn._is_connected is True
    assert btn._is_connecting is False
    assert btn._button.bgcolor == "#EDE9FE"
    assert btn._button.opacity == 1.0


def test_disconnected_state_styling():
    btn = _button()
    btn.set_disconnected("Disconnected")
    assert btn._is_connected is False
    assert btn._is_connecting is False
    assert btn._button.bgcolor == "#EDE9FE"
    assert btn._button.opacity == 1.0
