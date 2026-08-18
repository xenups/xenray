"""SNI Spoof settings + controller tests (WS1).

Verifies the SettingsRepository SNI spoof key persistence contract and the
SniSpoofController audit trail (persist + publish on every change).
"""

from __future__ import annotations

from unittest.mock import Mock

from src.core.event_bus import TOPIC_SNI_SPOOF_CHANGED, event_bus
from src.repositories.settings_repository import SettingsRepository
from src.ui.controllers.sni_spoof_controller import SniSpoofController


class TestSniSpoofSettingsRepository:
    """SNI spoof key persistence (defaults + round-trip + port range checks)."""

    def test_enabled_defaults_to_false(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        assert repo.get_sni_spoof_enabled() is False

    def test_enabled_round_trip(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        repo.set_sni_spoof_enabled(True)
        assert repo.get_sni_spoof_enabled() is True
        repo.set_sni_spoof_enabled(False)
        assert repo.get_sni_spoof_enabled() is False

    def test_enabled_default_false_across_instances(self, tmp_path):
        SettingsRepository(str(tmp_path))
        repo2 = SettingsRepository(str(tmp_path))
        assert repo2.get_sni_spoof_enabled() is False

    def test_fake_sni_default(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        assert repo.get_sni_fake_sni() == "chatgpt.com"

    def test_fake_sni_round_trip(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        repo.set_sni_fake_sni("mci.ir")
        assert repo.get_sni_fake_sni() == "mci.ir"
        assert SettingsRepository(str(tmp_path)).get_sni_fake_sni() == "mci.ir"

    def test_connect_ip_default(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        assert repo.get_sni_connect_ip() == "185.193.30.94"

    def test_connect_ip_round_trip(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        repo.set_sni_connect_ip("1.2.3.4")
        assert repo.get_sni_connect_ip() == "1.2.3.4"

    def test_connect_port_default(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        assert repo.get_sni_connect_port() == 443

    def test_connect_port_round_trip(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        repo.set_sni_connect_port(8443)
        assert repo.get_sni_connect_port() == 8443
        assert SettingsRepository(str(tmp_path)).get_sni_connect_port() == 8443

    def test_connect_port_rejects_out_of_range(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        repo.set_sni_connect_port(80)  # below 1024
        assert repo.get_sni_connect_port() == 443
        repo.set_sni_connect_port(70000)  # above 65535
        assert repo.get_sni_connect_port() == 443

    def test_connect_port_falls_back_on_garbage_file(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        repo._write("sni_connect_port.txt", "not-a-port")
        assert repo.get_sni_connect_port() == 443

    def test_listen_host_default_and_round_trip(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        assert repo.get_sni_listen_host() == "127.0.0.1"
        repo.set_sni_listen_host("0.0.0.0")
        assert repo.get_sni_listen_host() == "0.0.0.0"

    def test_listen_port_default_and_range_check(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        assert repo.get_sni_listen_port() == 40443
        repo.set_sni_listen_port(51443)
        assert repo.get_sni_listen_port() == 51443
        repo.set_sni_listen_port(1023)  # below range -> ignored
        assert repo.get_sni_listen_port() == 51443


class TestSniSpoofController:
    """Controller: reads repo on init, set_* persists + publishes the topic."""

    def test_init_reads_repo_state(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        repo.set_sni_spoof_enabled(True)
        repo.set_sni_fake_sni("mci.ir")
        repo.set_sni_connect_ip("1.2.3.4")
        repo.set_sni_connect_port(8443)
        ctrl = SniSpoofController(app_context=Mock(settings=repo))
        assert ctrl.enabled is True
        assert ctrl.fake_sni == "mci.ir"
        assert ctrl.connect_ip == "1.2.3.4"
        assert ctrl.connect_port == 8443

    def test_set_enabled_persists_and_publishes(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        ctx = Mock(settings=repo)
        ctrl = SniSpoofController(app_context=ctx)
        received = []

        def listener(data):
            received.append(data)

        event_bus.subscribe(TOPIC_SNI_SPOOF_CHANGED, listener)
        try:
            ctrl.set_enabled(True)
        finally:
            event_bus.unsubscribe(TOPIC_SNI_SPOOF_CHANGED, listener)

        assert repo.get_sni_spoof_enabled() is True
        assert ctrl.enabled is True
        assert len(received) == 1
        assert received[0]["enabled"] is True

    def test_set_fake_sni_persists_and_publishes(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        ctrl = SniSpoofController(app_context=Mock(settings=repo))
        received = []

        def listener(data):
            received.append(data)

        event_bus.subscribe(TOPIC_SNI_SPOOF_CHANGED, listener)
        try:
            ctrl.set_fake_sni("mci.ir")
        finally:
            event_bus.unsubscribe(TOPIC_SNI_SPOOF_CHANGED, listener)

        assert repo.get_sni_fake_sni() == "mci.ir"
        assert ctrl.fake_sni == "mci.ir"
        assert received[0]["fake_sni"] == "mci.ir"

    def test_set_connect_port_persists_and_publishes(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        ctrl = SniSpoofController(app_context=Mock(settings=repo))
        received = []

        def listener(data):
            received.append(data)

        event_bus.subscribe(TOPIC_SNI_SPOOF_CHANGED, listener)
        try:
            ctrl.set_connect_port(8443)
        finally:
            event_bus.unsubscribe(TOPIC_SNI_SPOOF_CHANGED, listener)

        assert repo.get_sni_connect_port() == 8443
        assert received[0]["connect_port"] == 8443

    def test_publish_payload_contains_all_keys(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        ctrl = SniSpoofController(app_context=Mock(settings=repo))
        received = []

        def listener(data):
            received.append(data)

        event_bus.subscribe(TOPIC_SNI_SPOOF_CHANGED, listener)
        try:
            ctrl.set_listen_port(51443)
        finally:
            event_bus.unsubscribe(TOPIC_SNI_SPOOF_CHANGED, listener)

        payload = received[0]
        for key in (
            "enabled",
            "fake_sni",
            "connect_ip",
            "connect_port",
            "listen_host",
            "listen_port",
        ):
            assert key in payload
