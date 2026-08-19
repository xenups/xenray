"""Tests for the LAN proxy sharing feature."""

from unittest.mock import MagicMock, patch

import pytest

from src.core.constants import LAN_FIREWALL_RULE_NAME, LAN_PRIVATE_RANGES
from src.repositories.settings_repository import SettingsRepository
from src.services.core_engines.xray_config_processor import XrayConfigProcessor
from src.utils.network_interface import NetworkInterfaceDetector


class TestSettingsRepository:
    """allow_lan persistence (default off)."""

    def test_allow_lan_defaults_to_false(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        assert repo.get_allow_lan() is False

    def test_allow_lan_round_trip(self, tmp_path):
        repo = SettingsRepository(str(tmp_path))
        repo.set_allow_lan(True)
        assert repo.get_allow_lan() is True
        repo.set_allow_lan(False)
        assert repo.get_allow_lan() is False


class TestEnsureInboundsListen:
    """SOCKS/HTTP inbounds bind to 0.0.0.0 only when LAN sharing is on."""

    def _processor(self, allow_lan: bool) -> XrayConfigProcessor:
        ctx = MagicMock()
        ctx.settings.get_proxy_port.return_value = 10805
        ctx.settings.get_allow_lan.return_value = allow_lan
        return XrayConfigProcessor(ctx)

    def test_listen_localhost_when_lan_off(self):
        proc = self._processor(allow_lan=False)
        config = {"inbounds": []}
        proc._ensure_inbounds(config)
        socks = next(ib for ib in config["inbounds"] if ib.get("protocol") == "socks")
        http = next(ib for ib in config["inbounds"] if ib.get("protocol") == "http")
        assert socks["listen"] == "127.0.0.1"
        assert http["listen"] == "127.0.0.1"

    def test_listen_all_interfaces_when_lan_on(self):
        proc = self._processor(allow_lan=True)
        config = {"inbounds": []}
        proc._ensure_inbounds(config)
        socks = next(ib for ib in config["inbounds"] if ib.get("protocol") == "socks")
        http = next(ib for ib in config["inbounds"] if ib.get("protocol") == "http")
        assert socks["listen"] == "0.0.0.0"
        assert http["listen"] == "0.0.0.0"

    def test_existing_inbound_listen_updated(self):
        proc = self._processor(allow_lan=True)
        config = {
            "inbounds": [
                {
                    "tag": "socks",
                    "protocol": "socks",
                    "port": 9999,
                    "listen": "127.0.0.1",
                    "settings": {},
                }
            ]
        }
        proc._ensure_inbounds(config)
        socks = next(ib for ib in config["inbounds"] if ib.get("protocol") == "socks")
        assert socks["listen"] == "0.0.0.0"
        assert socks["port"] == 10805


class TestFirewallManager:
    """Firewall rule add/check/remove via the OS firewall adapter."""

    def _adapter(self):
        from src.platform.windows.firewall import WindowsFirewallAdapter

        return WindowsFirewallAdapter(rule_name=LAN_FIREWALL_RULE_NAME)

    @patch("src.platform.windows.firewall._is_windows", return_value=True)
    def test_add_rule(self, mock_platform):
        adapter = self._adapter()
        with (
            patch(
                "src.platform.windows.firewall.WindowsFirewallAdapter.check_lan_firewall_rule",
                return_value=False,
            ),
            patch("src.platform.windows.firewall.WindowsFirewallAdapter._run", return_value="") as mock_run,
        ):
            ok = adapter.add_lan_firewall_rule([10805, 10809])
        assert ok is True
        cmd = mock_run.call_args[0][0]
        assert f"name={LAN_FIREWALL_RULE_NAME}" in cmd
        assert "localport=10805,10809" in cmd

    @patch("src.platform.windows.firewall._is_windows", return_value=True)
    def test_add_rule_skips_if_exists(self, mock_platform):
        adapter = self._adapter()
        with (
            patch(
                "src.platform.windows.firewall.WindowsFirewallAdapter.check_lan_firewall_rule",
                return_value=True,
            ),
            patch("src.platform.windows.firewall.WindowsFirewallAdapter._run") as mock_run,
        ):
            ok = adapter.add_lan_firewall_rule([10805])
        assert ok is True
        mock_run.assert_not_called()

    @patch("src.platform.windows.firewall._is_windows", return_value=True)
    def test_remove_rule(self, mock_platform):
        adapter = self._adapter()
        with (
            patch(
                "src.platform.windows.firewall.WindowsFirewallAdapter.check_lan_firewall_rule",
                return_value=True,
            ),
            patch("src.platform.windows.firewall.WindowsFirewallAdapter._run", return_value="") as mock_run,
        ):
            adapter.remove_lan_firewall_rule()
        cmd = mock_run.call_args[0][0]
        assert f"name={LAN_FIREWALL_RULE_NAME}" in cmd

    @patch("src.platform.windows.firewall._is_windows", return_value=False)
    def test_non_windows_skips(self, mock_platform):
        adapter = self._adapter()
        with patch("src.platform.windows.firewall.WindowsFirewallAdapter._run") as mock_run:
            assert adapter.add_lan_firewall_rule([10805]) is False
            adapter.remove_lan_firewall_rule()
        mock_run.assert_not_called()


class TestGetPrimaryLanIp:
    """LAN IP discovery is systemic: only physical, up, gateway-bearing
    adapters (from nic_detect / IP Helper) qualify."""

    @patch("src.platform.windows.network.get_physical_nic_candidates")
    def test_returns_first_private_ip(self, mock_cands):
        mock_cands.return_value = [
            {"name": "Wi-Fi", "ip": "192.168.1.15", "iftype": 71, "operstatus": 1, "gateway": True},
            {"name": "Ethernet", "ip": "10.57.20.22", "iftype": 6, "operstatus": 1, "gateway": True},
        ]
        assert NetworkInterfaceDetector.get_primary_lan_ip() == "192.168.1.15"

    @patch("src.platform.windows.network.get_physical_nic_candidates")
    def test_ignores_loopback(self, mock_cands):
        # Loopback is rejected by the private-IPv4 check; physical gateway NIC wins.
        mock_cands.return_value = [
            {"name": "Ethernet", "ip": "192.168.70.125", "iftype": 6, "operstatus": 1, "gateway": True},
        ]
        assert NetworkInterfaceDetector.get_primary_lan_ip() == "192.168.70.125"


class TestSingboxLanRoutes:
    """Private LAN range routes added when LAN sharing is enabled."""

    def _service(self):
        from src.services.core_engines.singbox_service import SingboxService

        return SingboxService()

    @patch("subprocess.run")
    @patch("src.utils.platform_utils.PlatformUtils.get_platform", return_value="windows")
    def test_add_lan_routes(self, mock_platform, mock_run):
        # H3: successful deletions (rc==0) are removed; failed ones are kept
        # for retry. Make every simulated delete succeed so all drain.
        mock_run.return_value.returncode = 0
        svc = self._service()
        svc._add_lan_routes("192.168.1.1")
        assert len(svc._added_lan_routes) == len(LAN_PRIVATE_RANGES)
        # cleanup removes them
        svc._cleanup_lan_routes()
        assert svc._added_lan_routes == []


class TestOrchestratorLanWiring:
    """allow_lan is threaded through sing-box start + firewall lifecycle."""

    @pytest.fixture
    def orchestrator(self):
        from src.core.connection_orchestrator import ConnectionOrchestrator

        self.mock_app_context = MagicMock()
        self.mock_net_val = MagicMock()
        self.mock_xray_proc = MagicMock()
        self.mock_xray_svc = MagicMock()
        self.mock_legacy = MagicMock()
        self.mock_singbox = MagicMock()
        self.mock_legacy.is_legacy.return_value = False
        return ConnectionOrchestrator(
            self.mock_app_context,
            self.mock_net_val,
            self.mock_xray_proc,
            self.mock_xray_svc,
            self.mock_legacy,
            singbox_service=self.mock_singbox,
        )

    def test_start_singbox_passes_allow_lan(self, orchestrator):
        orchestrator._app_context.settings.get_allow_lan.return_value = True
        orchestrator._app_context.settings.get_routing_country.return_value = "ir"
        orchestrator._app_context.routing.load_rules.return_value = {}
        orchestrator._xray_processor.is_quic_transport.return_value = False
        orchestrator._xray_processor.get_proxy_server_ip.return_value = "1mobility.example.com"
        orchestrator._singbox_service.start.return_value = 1234
        with patch("src.utils.network_utils.NetworkUtils.detect_optimal_mtu", return_value=1420):
            orchestrator._start_singbox({"p": True}, 10805, None)
        orchestrator._singbox_service.start.assert_called_once()
        assert orchestrator._singbox_service.start.call_args.kwargs["allow_lan"] is True

    @patch("src.services.connection.connection_tester.ConnectionTester.test_connection_sync")
    @patch("builtins.open", new_callable=MagicMock)
    def test_success_ensures_firewall_rule(self, mock_open, mock_conn_test, orchestrator):
        orchestrator._app_context.settings.get_allow_lan.return_value = True
        orchestrator._xray_processor.process_config.return_value = {"p": True}
        orchestrator._xray_processor.get_socks_port.return_value = 10805
        orchestrator._xray_service.start.return_value = 1234
        mock_conn_test.return_value = (True, "50ms", None)

        with patch.object(orchestrator, "_ensure_lan_firewall_rule") as mock_ensure:
            status, _ = orchestrator._attempt_single_connection(
                "standard", {"x": 1}, "proxy", False, "config.json", None
            )

        assert status == orchestrator.ATTEMPT_SUCCESS
        mock_ensure.assert_called_once_with(10805)

    def test_teardown_removes_firewall_rule(self, orchestrator):
        with patch.object(orchestrator, "_remove_lan_firewall_rule") as mock_remove:
            orchestrator.teardown_connection({"xray_pid": 1})
        mock_remove.assert_called_once()


class TestLanSharingCardUI:
    """LAN proxy sharing top bar status chip/badge UI tests."""

    @pytest.fixture
    def app_context(self):
        ctx = MagicMock()
        ctx.settings.get_proxy_port.return_value = 10805
        return ctx

    @patch("src.utils.network_interface.NetworkInterfaceDetector.get_primary_lan_ip", return_value="192.168.70.125")
    def test_initial_state(self, mock_ip, app_context):
        from src.ui.components.lan.lan_sharing_card import LanSharingCard

        card = LanSharingCard(app_context)
        assert card.visible is False

    @patch("src.utils.network_interface.NetworkInterfaceDetector.get_primary_lan_ip", return_value="192.168.70.125")
    def test_set_visible_shows_badge(self, mock_ip, app_context):
        from src.ui.components.lan.lan_sharing_card import LanSharingCard

        card = LanSharingCard(app_context)
        card.set_visible(True)
        assert card.visible is True
        assert card._label_text.value == "LAN 192.168.70.125"

    @patch("src.utils.network_interface.NetworkInterfaceDetector.get_primary_lan_ip", return_value="192.168.70.125")
    def test_open_dialog_opens_modal(self, mock_ip, app_context):
        from src.ui.components.lan.lan_sharing_card import LanSharingCard

        card = LanSharingCard(app_context)
        mock_page = MagicMock()
        card._page = mock_page

        card._open_dialog()
        mock_page.show_dialog.assert_called_once()


class TestLanSharingUnifiedToggle:
    """set_lan_sharing_enabled persists, applies firewall rules, and broadcasts."""

    @pytest.fixture
    def controller(self):
        from src.ui.controllers.lan_sharing_controller import LanSharingController

        ctx = MagicMock()
        ctx.settings.get_proxy_port.return_value = 10805
        ctx.settings.get_allow_lan.return_value = False
        return LanSharingController(app_context=ctx), ctx

    def test_enable_persists_firewall_and_publishes(self, controller, monkeypatch):
        from src.core.event_bus import TOPIC_LAN_SHARING_CHANGED, event_bus

        ctrl, ctx = controller
        received = []

        def listener(data):
            received.append(data)

        event_bus.subscribe(TOPIC_LAN_SHARING_CHANGED, listener)
        try:
            with patch("src.utils.firewall_manager.FirewallManager.add_lan_firewall_rule") as mock_add:
                ctrl.set_lan_sharing_enabled(True)
        finally:
            event_bus.unsubscribe(TOPIC_LAN_SHARING_CHANGED, listener)

        ctx.settings.set_allow_lan.assert_called_once_with(True)
        mock_add.assert_called_once_with([10805, 10809])
        assert received == [{"enabled": True}]

    def test_disable_removes_firewall_and_publishes(self, controller):
        from src.core.event_bus import TOPIC_LAN_SHARING_CHANGED, event_bus

        ctrl, ctx = controller
        received = []

        def listener(data):
            received.append(data)

        event_bus.subscribe(TOPIC_LAN_SHARING_CHANGED, listener)
        try:
            with patch("src.utils.firewall_manager.FirewallManager.remove_lan_firewall_rule") as mock_remove:
                ctrl.set_lan_sharing_enabled(False)
        finally:
            event_bus.unsubscribe(TOPIC_LAN_SHARING_CHANGED, listener)

        ctx.settings.set_allow_lan.assert_called_once_with(False)
        mock_remove.assert_called_once()
        assert received == [{"enabled": False}]
