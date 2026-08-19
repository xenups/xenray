"""Tests: SNI-spoof Zero-Flag Pure Event & FSM Standby Lifecycle."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from src.core.fsm.connection_fsm import ConnectionState, connection_fsm
from src.services.sni_spoof.sni_spoof_service import (
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_STOPPED,
    SniSpoofService,
    reset_shared_service_for_tests,
)


@pytest.fixture(autouse=True)
def _clean_shared():
    """Isolate each test from the process-shared SniSpoofService instance and reset FSM."""
    reset_shared_service_for_tests()
    connection_fsm.reset()
    yield
    reset_shared_service_for_tests()
    connection_fsm.reset()


def _make_service():
    """Return a SniSpoofService with the listener loop mocked out."""
    svc = SniSpoofService.__new__(SniSpoofService)
    svc._settings_repo = None
    from src.core.event_bus import EventBus

    svc._event_bus = EventBus.get_instance()
    svc._task = None
    svc.status = STATUS_STOPPED
    svc._watcher_stop = threading.Event()
    svc._watcher = None
    svc._watcher_lock = threading.Lock()
    svc._loop = None
    svc._loop_thread = None
    svc._loop_ready = threading.Event()
    svc._engine = None

    def _fake_start_loop():
        svc._task = MagicMock()
        svc._task.done.return_value = False

    svc._start_listener_loop = _fake_start_loop
    svc._shutdown_listener_loop = MagicMock()
    svc._publish = MagicMock()
    svc._build_engine_from_config = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# SniSpoofService.start(enable_pid_watcher: bool)
# ---------------------------------------------------------------------------


class TestServiceStartUnified:
    def test_start_without_watcher_starts_listener_only(self, monkeypatch):
        svc = _make_service()
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service._prerequisites_ok",
            lambda: (True, ""),
        )
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service.build_config",
            lambda *a: {"LISTEN_HOST": "127.0.0.1", "LISTEN_PORT": 40443},
        )
        monkeypatch.setattr("src.services.sni_spoof.sni_spoof_service.configure", MagicMock())

        result = svc.start(enable_pid_watcher=False)

        assert result is True
        assert svc.running is True
        assert svc.status == STATUS_RUNNING
        assert svc.pid_watcher_active is False

    def test_start_with_watcher_attaches_pid_thread(self, monkeypatch):
        svc = _make_service()
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service._prerequisites_ok",
            lambda: (True, ""),
        )
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service.build_config",
            lambda *a: {"LISTEN_HOST": "127.0.0.1", "LISTEN_PORT": 40443},
        )
        monkeypatch.setattr("src.services.sni_spoof.sni_spoof_service.configure", MagicMock())

        result = svc.start(enable_pid_watcher=True)

        assert result is True
        assert svc.running is True
        assert svc.pid_watcher_active is True
        svc._watcher_stop.set()

    def test_start_fails_gracefully_when_prereqs_missing(self, monkeypatch):
        svc = _make_service()
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service._prerequisites_ok",
            lambda: (False, "missing admin privileges"),
        )

        result = svc.start(enable_pid_watcher=False)

        assert result is False
        assert svc.status == STATUS_FAILED
        assert svc.running is False

    def test_promote_standby_to_connected_attaches_watcher_without_restarting_loop(self, monkeypatch):
        svc = _make_service()
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service._prerequisites_ok",
            lambda: (True, ""),
        )
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service.build_config",
            lambda *a: {"LISTEN_HOST": "127.0.0.1", "LISTEN_PORT": 40443},
        )
        monkeypatch.setattr("src.services.sni_spoof.sni_spoof_service.configure", MagicMock())

        spawn_count = [0]
        orig_start_loop = svc._start_listener_loop

        def _count_spawn():
            spawn_count[0] += 1
            orig_start_loop()

        svc._start_listener_loop = _count_spawn

        # Start in standby mode
        svc.start(enable_pid_watcher=False)
        assert spawn_count[0] == 1
        assert svc.pid_watcher_active is False

        # Promote to connected mode
        svc.start(enable_pid_watcher=True)
        assert spawn_count[0] == 1  # No loop restart!
        assert svc.pid_watcher_active is True
        svc._watcher_stop.set()

    def test_demote_connected_to_standby_detaches_watcher_without_restarting_loop(self, monkeypatch):
        svc = _make_service()
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service._prerequisites_ok",
            lambda: (True, ""),
        )
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service.build_config",
            lambda *a: {"LISTEN_HOST": "127.0.0.1", "LISTEN_PORT": 40443},
        )
        monkeypatch.setattr("src.services.sni_spoof.sni_spoof_service.configure", MagicMock())

        spawn_count = [0]
        orig_start_loop = svc._start_listener_loop

        def _count_spawn():
            spawn_count[0] += 1
            orig_start_loop()

        svc._start_listener_loop = _count_spawn

        # Start in connected mode
        svc.start(enable_pid_watcher=True)
        assert spawn_count[0] == 1
        assert svc.pid_watcher_active is True

        # Demote to standby mode on disconnect
        svc.start(enable_pid_watcher=False)
        assert spawn_count[0] == 1  # No loop restart!
        assert svc.pid_watcher_active is False


class TestServiceUpdateTarget:
    def test_update_target_updates_listener_globals(self):
        svc = _make_service()
        import src.services.sni_spoof.listener as lmod

        svc.update_target("1.2.3.4", 8443)
        assert lmod.CONNECT_IP == "1.2.3.4"
        assert lmod.CONNECT_PORT == 8443


class TestServiceStop:
    def test_stop_cleans_watcher_and_loop(self, monkeypatch):
        svc = _make_service()
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service._prerequisites_ok",
            lambda: (True, ""),
        )
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service.build_config",
            lambda *a: {"LISTEN_HOST": "127.0.0.1", "LISTEN_PORT": 40443},
        )
        monkeypatch.setattr("src.services.sni_spoof.sni_spoof_service.configure", MagicMock())

        svc.start(enable_pid_watcher=True)
        assert svc.pid_watcher_active is True

        svc.stop()
        assert svc.pid_watcher_active is False
        assert svc.status == STATUS_STOPPED


# ---------------------------------------------------------------------------
# bridge.py Pure FSM & EventBus Policies
# ---------------------------------------------------------------------------


class TestBridgePureEventFsmPolicy:
    def test_enable_toggle_reads_fsm_standby_when_disconnected(self, monkeypatch):
        """When FSM is DISCONNECTED, enable toggle starts service with enable_pid_watcher=False."""
        from src.services.sni_spoof import bridge

        bridge.reset_sni_spoof_bridge_for_tests()
        connection_fsm.reset()
        assert connection_fsm.state == ConnectionState.DISCONNECTED

        start_calls = []
        fake_service = MagicMock()
        fake_service.running = False
        fake_service.start = lambda enable_pid_watcher=False: start_calls.append(enable_pid_watcher)

        monkeypatch.setattr("src.services.sni_spoof.bridge.get_sni_spoof_service", lambda: fake_service)

        bridge._on_sni_spoof_changed({"enabled_changed": True, "enabled": True})

        assert start_calls == [False]

    def test_enable_toggle_reads_fsm_connected_when_connected(self, monkeypatch):
        """When FSM is CONNECTED, enable toggle starts service with enable_pid_watcher=True."""
        from src.services.sni_spoof import bridge

        bridge.reset_sni_spoof_bridge_for_tests()
        connection_fsm.transition_to(ConnectionState.STARTING, force=True)
        connection_fsm.transition_to(ConnectionState.PREPARING, force=True)
        connection_fsm.transition_to(ConnectionState.CONNECTED, force=True)
        assert connection_fsm.state == ConnectionState.CONNECTED

        start_calls = []
        fake_service = MagicMock()
        fake_service.running = False
        fake_service.start = lambda enable_pid_watcher=False: start_calls.append(enable_pid_watcher)

        monkeypatch.setattr("src.services.sni_spoof.bridge.get_sni_spoof_service", lambda: fake_service)

        bridge._on_sni_spoof_changed({"enabled_changed": True, "enabled": True})

        assert start_calls == [True]

    def test_disable_toggle_stops_service(self, monkeypatch):
        from src.services.sni_spoof import bridge

        bridge.reset_sni_spoof_bridge_for_tests()

        stopped = []
        fake_service = MagicMock()
        fake_service.stop = lambda: stopped.append(True)

        monkeypatch.setattr("src.services.sni_spoof.bridge.get_sni_spoof_service", lambda: fake_service)

        bridge._on_sni_spoof_changed({"enabled_changed": True, "enabled": False})

        assert len(stopped) == 1

    def test_connect_event_promotes_with_pid_watcher_when_enabled(self, monkeypatch):
        from src.services.sni_spoof import bridge

        bridge.reset_sni_spoof_bridge_for_tests()

        start_calls = []
        fake_service = MagicMock()
        fake_service.start = lambda enable_pid_watcher=False: start_calls.append(enable_pid_watcher)

        monkeypatch.setattr("src.services.sni_spoof.bridge.get_sni_spoof_service", lambda: fake_service)
        monkeypatch.setattr("src.services.sni_spoof.bridge._sni_spoof_is_enabled", lambda: True)

        bridge._on_connection_state_changed({"state": "connected"})

        assert start_calls == [True]

    def test_disconnect_event_demotes_to_standby_when_enabled(self, monkeypatch):
        from src.services.sni_spoof import bridge

        bridge.reset_sni_spoof_bridge_for_tests()

        start_calls = []
        fake_service = MagicMock()
        fake_service.start = lambda enable_pid_watcher=False: start_calls.append(enable_pid_watcher)

        monkeypatch.setattr("src.services.sni_spoof.bridge.get_sni_spoof_service", lambda: fake_service)
        monkeypatch.setattr("src.services.sni_spoof.bridge._sni_spoof_is_enabled", lambda: True)

        bridge._on_connection_state_changed({"state": "disconnected"})

        assert start_calls == [False]

    def test_disconnect_event_stops_when_sni_disabled(self, monkeypatch):
        from src.services.sni_spoof import bridge

        bridge.reset_sni_spoof_bridge_for_tests()

        stopped = []
        fake_service = MagicMock()
        fake_service.stop = lambda: stopped.append(True)

        monkeypatch.setattr("src.services.sni_spoof.bridge.get_sni_spoof_service", lambda: fake_service)
        monkeypatch.setattr("src.services.sni_spoof.bridge._sni_spoof_is_enabled", lambda: False)

        bridge._on_connection_state_changed({"state": "disconnected"})

        assert len(stopped) == 1

    def test_config_edit_triggers_update_target(self, monkeypatch):
        from src.services.sni_spoof import bridge

        bridge.reset_sni_spoof_bridge_for_tests()

        updated = []
        fake_service = MagicMock()
        fake_service.running = True
        fake_service.update_target = lambda h, p: updated.append((h, p))

        monkeypatch.setattr("src.services.sni_spoof.bridge.get_sni_spoof_service", lambda: fake_service)

        bridge._on_sni_spoof_changed({"CONNECT_IP": "9.9.9.9", "CONNECT_PORT": 9443})

        assert updated == [("9.9.9.9", 9443)]


# ---------------------------------------------------------------------------
# Startup Warmup Manager
# ---------------------------------------------------------------------------


class TestStartupWarmupManagerStandby:
    @pytest.mark.asyncio
    async def test_warmup_starts_standby_with_enable_pid_watcher_false(self, monkeypatch):
        from src.core.startup_warmup_manager import StartupWarmupManager

        mgr = StartupWarmupManager()

        start_calls = []
        fake_repo = MagicMock()
        fake_repo.get_sni_spoof_enabled.return_value = True
        fake_service = MagicMock()
        fake_service.running = False
        fake_service.start = lambda enable_pid_watcher=False: start_calls.append(enable_pid_watcher)

        monkeypatch.setattr(
            "src.repositories.settings_repository.SettingsRepository",
            lambda *a: fake_repo,
        )
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service.get_sni_spoof_service",
            lambda *a: fake_service,
        )

        await mgr._warmup_sni_spoof_standby()

        assert start_calls == [False]

    @pytest.mark.asyncio
    async def test_warmup_skips_when_disabled(self, monkeypatch):
        from src.core.startup_warmup_manager import StartupWarmupManager

        mgr = StartupWarmupManager()

        start_calls = []
        fake_repo = MagicMock()
        fake_repo.get_sni_spoof_enabled.return_value = False
        fake_service = MagicMock()
        fake_service.running = False
        fake_service.start = lambda enable_pid_watcher=False: start_calls.append(enable_pid_watcher)

        monkeypatch.setattr(
            "src.repositories.settings_repository.SettingsRepository",
            lambda *a: fake_repo,
        )
        monkeypatch.setattr(
            "src.services.sni_spoof.sni_spoof_service.get_sni_spoof_service",
            lambda *a: fake_service,
        )

        await mgr._warmup_sni_spoof_standby()

        assert len(start_calls) == 0
