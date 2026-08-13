"""Tests for QR skeleton loading shown while the LAN-sharing QR generates."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.ui.components.lan.qr_card import QRCard
from src.ui.pages.lan_sharing_page import LanSharingPage


def _attached_card():
    """QRCard whose _refresh() is observable (simulates an attached page)."""
    card = QRCard(is_rtl=False)
    card._qr_box_update_called = False
    orig_refresh = card._refresh

    def _tracked_refresh():
        card._qr_box_update_called = True
        orig_refresh()

    card._refresh = _tracked_refresh
    return card


def test_qr_card_show_loading_builds_skeleton():
    """show_loading must swap the QR box content to the skeleton (not the image)."""
    card = _attached_card()

    card.show_loading()

    # The box should now hold the skeleton column (finders + label), not an Image
    content = card._qr_box.content
    assert isinstance(content, __import__("flet").Column)
    assert card._qr_box_update_called


def test_qr_card_update_qr_replaces_skeleton_with_image():
    """update_qr must replace the skeleton with the actual QR image."""
    card = _attached_card()

    card.show_loading()
    assert not card.is_qr_shown

    card.update_qr("aGVsbG8=")
    assert card.is_qr_shown is True
    assert card._qr_box.bgcolor == "white"


def test_toggle_enabled_shows_loading_before_async():
    """Enabling the LAN switch must show the skeleton BEFORE the QR resolves."""
    controller = MagicMock()
    controller.get_local_ip.return_value = "192.168.1.10"
    controller.get_http_port.return_value = 8080
    controller.get_socks_port.return_value = 10808
    controller.get_allow_lan.return_value = False
    controller.generate_qr.return_value = "c2tlbGV0b24="

    # Build page with a fake controller
    page = LanSharingPage.__new__(LanSharingPage)
    page.is_rtl = False
    page._controller = controller
    page.local_ip = "192.168.1.10"
    page.http_port = 8080
    page.socks_port = 10808
    page.allow_lan = False
    page._on_lan_toggle = None
    page._ip_chip = MagicMock()  # used by _on_toggle_change
    page._master_switch = MagicMock()

    # Build the real QRCard and wire it
    page._qr_card = _attached_card()
    page._refresh_qr_async = MagicMock()

    # Simulate toggling the switch ON
    event = MagicMock()
    event.control.value = True
    page._on_toggle_change(event)

    # Skeleton must be shown immediately (before the async QR lands)
    assert not page._qr_card.is_qr_shown
    assert page._qr_card._qr_box_update_called
    page._refresh_qr_async.assert_called_once_with(True)


def test_generate_qr_async_yields_before_worker():
    """_generate_qr_async must yield (sleep) so the skeleton can render."""
    import asyncio

    app_context = MagicMock()
    controller = MagicMock()
    controller.generate_qr.return_value = "ZmFrZQ=="

    page = LanSharingPage.__new__(LanSharingPage)
    page._controller = controller
    page.local_ip = "192.168.1.10"
    page.http_port = 8080
    page._qr_card = MagicMock()

    async def run():
        await page._generate_qr_async()
        page._qr_card.update_qr.assert_called_once_with("ZmFrZQ==")

    asyncio.run(run())
