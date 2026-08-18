"""End-to-end tests for the SNI-spoof config flow, lifecycle bridge, and the
dedicated-loop robustness fix.

These cover the three review findings:
  1. Persisted config reaches the real listener (listener.configure wired into
     SniSpoofService.start).
  2. TOPIC_SNI_SPOOF_CHANGED drives the shared service (start gated on an active
     connection; stop always) and TOPIC_CONNECTION_STATE_CHANGED stops it on
     disconnect. The view's status chip reflects service status events.
  3. start() works from a worker thread that has no running asyncio loop (the
     service owns a dedicated loop in its own thread).
"""

import asyncio
import threading
from unittest.mock import Mock, patch

import pytest

from src.services.sni_spoof import bridge as bridge_mod
from src.services.sni_spoof import listener as listener_mod
from src.services.sni_spoof import sni_spoof_service as svc_mod
from src.services.sni_spoof.sni_spoof_service import SniSpoofService


class FakeRepo:
    def get_sni_fake_sni(self):
        return "fake.example.com"

    def get_sni_connect_ip(self):
        return "10.0.0.2"

    def get_sni_connect_port(self):
        return 8443

    def get_sni_listen_host(self):
        return "0.0.0.0"

    def get_sni_listen_port(self):
        return 44443


@pytest.fixture(autouse=True)
def _isolate_bridge():
    svc_mod.reset_shared_service_for_tests()
    bridge_mod.reset_sni_spoof_bridge_for_tests()
    yield
    svc_mod.reset_shared_service_for_tests()
    bridge_mod.reset_sni_spoof_bridge_for_tests()


def _snapshot_listener_globals():
    keys = ("FAKE_SNI", "CONNECT_IP", "CONNECT_PORT", "LISTEN_HOST", "LISTEN_PORT")
    return {k: getattr(listener_mod, k) for k in keys}


def _restore_listener_globals(snapshot):
    for k, v in snapshot.items():
        setattr(listener_mod, k, v)


# --------------------------------------------------------------------------- #
# 1. Persisted config reaches the listener via configure()
# --------------------------------------------------------------------------- #


def test_start_applies_persisted_config_to_listener(monkeypatch):
    class _DiskRepo:
        def get_sni_connect_ip(self):
            return "10.0.0.2"

        def get_sni_connect_port(self):
            return 8443

    monkeypatch.setattr(
        "src.repositories.settings_repository.SettingsRepository", lambda *a, **k: _DiskRepo()
    )
    snapshot = _snapshot_listener_globals()
    service = SniSpoofService(settings_repo=FakeRepo())
    try:
        with (
            patch.object(svc_mod, "_prerequisites_ok", return_value=(True, "")),
            patch.object(svc_mod, "run_listener"),
        ):
            assert service.start() is True
        assert listener_mod.FAKE_SNI == "fake.example.com"
        assert listener_mod.CONNECT_IP == "10.0.0.2"
        assert listener_mod.CONNECT_PORT == 8443
        assert listener_mod.LISTEN_HOST == "0.0.0.0"
        assert listener_mod.LISTEN_PORT == 44443
    finally:
        service.stop()
        _restore_listener_globals(snapshot)


# --------------------------------------------------------------------------- #
# 3. start() from a worker thread with no running asyncio loop
# --------------------------------------------------------------------------- #


def test_start_runs_from_worker_thread_without_loop():
    began = threading.Event()

    async def fake_listener():
        began.set()
        await asyncio.Event().wait()

    service = SniSpoofService(settings_repo=FakeRepo())
    result = {}

    def call_start():
        result["ok"] = service.start()

    try:
        with (
            patch.object(svc_mod, "_prerequisites_ok", return_value=(True, "")),
            patch.object(svc_mod, "run_listener", fake_listener),
        ):
            worker = threading.Thread(target=call_start)
            worker.start()
            worker.join(timeout=5)
        assert not worker.is_alive()
        assert result.get("ok") is True
        assert began.wait(5.0), "listener coroutine never started on the owned loop"
        assert service.running is True
    finally:
        service.stop()


# --------------------------------------------------------------------------- #
# 2. Lifecycle bridge: toggle + connection state drive start/stop
# --------------------------------------------------------------------------- #


class _FakeService:
    def __init__(self):
        self.start = Mock(return_value=True)
        self.stop = Mock()
        self.running = False


def test_toggle_enabled_with_active_connection_starts():
    fake = _FakeService()
    bridge_mod._connection_active = True
    with patch.object(bridge_mod, "get_sni_spoof_service", return_value=fake):
        bridge_mod._on_sni_spoof_changed({"enabled": True, "enabled_changed": True})
    fake.start.assert_called_once()


def test_toggle_enabled_without_active_connection_does_not_start():
    fake = _FakeService()
    bridge_mod._connection_active = False
    with patch.object(bridge_mod, "get_sni_spoof_service", return_value=fake):
        bridge_mod._on_sni_spoof_changed({"enabled": True, "enabled_changed": True})
    fake.start.assert_not_called()


def test_toggle_disabled_stops():
    fake = _FakeService()
    with patch.object(bridge_mod, "get_sni_spoof_service", return_value=fake):
        bridge_mod._on_sni_spoof_changed({"enabled": False, "enabled_changed": True})
    fake.stop.assert_called_once()


def test_field_edit_without_toggle_marker_is_ignored():
    """A plain config publish (any field edit) must not start/stop the service."""
    fake = _FakeService()
    with patch.object(bridge_mod, "get_sni_spoof_service", return_value=fake):
        bridge_mod._on_sni_spoof_changed({"enabled": False, "fake_sni": "x.com"})
    fake.start.assert_not_called()
    fake.stop.assert_not_called()


def test_toggle_event_without_enabled_field_is_ignored():
    fake = _FakeService()
    with patch.object(bridge_mod, "get_sni_spoof_service", return_value=fake):
        bridge_mod._on_sni_spoof_changed({"status": "running"})
    fake.start.assert_not_called()
    fake.stop.assert_not_called()


def test_connection_disconnected_stops_service():
    fake = _FakeService()
    with patch.object(bridge_mod, "get_sni_spoof_service", return_value=fake):
        bridge_mod._on_connection_state_changed({"state": "disconnected"})
    fake.stop.assert_called_once()


def test_connection_connected_does_not_stop():
    fake = _FakeService()
    with patch.object(bridge_mod, "get_sni_spoof_service", return_value=fake):
        bridge_mod._on_connection_state_changed({"state": "connected"})
    fake.stop.assert_not_called()


def test_lifecycle_bridge_wires_subscriptions():
    from src.core.event_bus import (
        TOPIC_CONNECTION_STATE_CHANGED,
        TOPIC_SNI_SPOOF_CHANGED,
        event_bus,
    )

    bridge_mod.install_sni_spoof_lifecycle_bridge()
    fake = _FakeService()
    with patch.object(bridge_mod, "get_sni_spoof_service", return_value=fake):
        event_bus.publish(
            TOPIC_SNI_SPOOF_CHANGED, {"enabled": False, "enabled_changed": True}
        )
        event_bus.publish(TOPIC_CONNECTION_STATE_CHANGED, {"state": "disconnected"})
    fake.stop.assert_any_call()


# --------------------------------------------------------------------------- #
# 2c. View status chip reacts to service status events
# --------------------------------------------------------------------------- #


def test_view_status_chip_updates_on_service_event():
    from src.ui.views.sni_spoof_view import SniSpoofView

    view = SniSpoofView(controller=Mock())
    try:
        chip_text = view._status_chip.content.controls[1]
        view._on_status_event({"status": "running"})
        assert chip_text.value == "Running"
        view._on_status_event({"status": "stopped"})
        assert chip_text.value == "Stopped"
    finally:
        view.dispose()
