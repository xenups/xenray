"""Tests for the OS abstraction layer (src/platform/).

Covers: factory adapter selection, the Windows firewall adapter (the real netsh
logic), the network adapter LAN-IP detection, the settings/process adapters, and
the no-op POSIX stubs. Business logic stays platform-agnostic.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.platform.constants import CMD_NETSH, TUN_ADAPTER_NAME
from src.platform.factory import (
    get_firewall_adapter,
    get_network_adapter,
    get_process_adapter,
    get_system_settings_adapter,
    get_tun_dns_configurator,
    get_tun_driver_adapter,
)
from src.platform.interfaces import (
    IFirewallAdapter,
    INetworkAdapter,
    IProcessAdapter,
    ISystemSettingsAdapter,
    ITunDnsConfigurator,
    ITunDriverAdapter,
)


class TestFactory:
    def test_windows_returns_win_adapters(self):
        with patch("src.platform.factory._is_windows", return_value=True):
            assert isinstance(get_tun_dns_configurator(), ITunDnsConfigurator)
            assert isinstance(get_network_adapter(), INetworkAdapter)
            assert isinstance(get_system_settings_adapter(), ISystemSettingsAdapter)
            assert isinstance(get_firewall_adapter(), IFirewallAdapter)
            assert isinstance(get_process_adapter(), IProcessAdapter)
            assert isinstance(get_tun_driver_adapter(), ITunDriverAdapter)

    def test_posix_returns_noop_or_posix(self):
        from src.platform.posix import NoopTunDnsConfigurator, PosixNetworkAdapter
        from src.platform.posix.tun_driver import NoopTunDriverAdapter

        with patch("src.platform.factory._is_windows", return_value=False):
            assert isinstance(get_tun_dns_configurator(), NoopTunDnsConfigurator)
            assert isinstance(get_network_adapter(), PosixNetworkAdapter)
            assert isinstance(get_tun_driver_adapter(), NoopTunDriverAdapter)
            # posix firewall returns False (unsupported)
            assert get_firewall_adapter().add_rule("x", 10805) is False


class TestFirewallAdapter:
    def _adapter(self):
        from src.platform.windows.firewall import WindowsFirewallAdapter

        return WindowsFirewallAdapter(rule_name="XenRay Inbound LAN Proxy")

    @patch("src.platform.windows.firewall._is_windows", return_value=True)
    def test_add_rule_uses_netsh_advfirewall(self, mock_platform):
        adapter = self._adapter()
        with (
            patch(
                "src.platform.windows.firewall.WindowsFirewallAdapter._run",
                return_value="",
            ) as mock_run,
        ):
            ok = adapter.add_lan_firewall_rule([10805, 10809])
        assert ok is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == CMD_NETSH
        assert "advfirewall" in cmd and "add" in cmd

    @patch("src.platform.windows.firewall._is_windows", return_value=False)
    def test_non_windows_returns_false(self, mock_platform):
        adapter = self._adapter()
        with patch("src.platform.windows.firewall.WindowsFirewallAdapter._run") as mock_run:
            assert adapter.add_lan_firewall_rule([10805]) is False
            adapter.remove_lan_firewall_rule()
        mock_run.assert_not_called()

    def test_noop_firewall_adapter(self):
        from src.platform.posix import NoopFirewallAdapter

        noop = NoopFirewallAdapter()
        assert noop.add_rule("test", 80) is False
        assert noop.remove_rule("test") is False
        assert noop.check_lan_firewall_rule() is False
        assert noop.add_lan_firewall_rule([10805]) is False
        assert noop.remove_lan_firewall_rule() is None

    def test_firewall_manager_delegation(self):
        from src.utils.firewall_manager import FirewallManager

        mock_adapter = MagicMock()
        mock_adapter.check_lan_firewall_rule.return_value = True
        mock_adapter.add_lan_firewall_rule.return_value = True

        with patch("src.utils.firewall_manager.get_firewall_adapter", return_value=mock_adapter):
            assert FirewallManager.check_lan_firewall_rule() is True
            assert FirewallManager.add_lan_firewall_rule([10805, 10809]) is True
            assert FirewallManager.allow_lan_sharing_ports(10805, http_port=10809) is True
            mock_adapter.add_lan_firewall_rule.assert_called_with([10805, 10809])

            assert FirewallManager.allow_lan_sharing_ports(10805) is True
            mock_adapter.add_lan_firewall_rule.assert_called_with([10805])

            assert FirewallManager.allow_lan_sharing_ports(0) is False

            FirewallManager.remove_lan_firewall_rule()
            mock_adapter.remove_lan_firewall_rule.assert_called_once()


class TestNetworkAdapter:
    def test_lan_ip_uses_ip_helper_candidates(self):
        from src.platform.windows.network import WindowsNetworkAdapter

        adapter = WindowsNetworkAdapter()
        with patch(
            "src.platform.windows.network.get_physical_nic_candidates",
            return_value=[{"name": "Ethernet", "ip": "192.168.70.125", "iftype": 6, "operstatus": 1, "gateway": True}],
        ):
            assert adapter.get_physical_lan_ip() == "192.168.70.125"

    def test_lan_ip_none_when_no_interface(self):
        from src.platform.windows.network import WindowsNetworkAdapter

        adapter = WindowsNetworkAdapter()
        with (
            patch("src.platform.windows.network.get_physical_nic_candidates", return_value=[]),
            patch("socket.socket", side_effect=OSError("Network unreachable")),
        ):
            assert adapter.get_physical_lan_ip() is None

    def test_windows_ping_mtu(self):
        from src.platform.windows.network import WindowsNetworkAdapter

        adapter = WindowsNetworkAdapter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            assert adapter.ping_mtu("8.8.8.8", 1400, 2) is True
            cmd = mock_run.call_args[0][0]
            assert cmd == ["ping", "-n", "1", "-w", "2000", "-f", "-l", "1400", "8.8.8.8"]

    def test_posix_ping_mtu_linux_and_macos(self):
        from src.platform.posix import PosixNetworkAdapter

        adapter = PosixNetworkAdapter()
        with patch("sys.platform", "linux"), patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            assert adapter.ping_mtu("8.8.8.8", 1400, 2) is True
            cmd = mock_run.call_args[0][0]
            assert cmd == ["ping", "-c", "1", "-W", "2", "-M", "do", "-s", "1400", "8.8.8.8"]

        with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            assert adapter.ping_mtu("8.8.8.8", 1400, 2) is True
            cmd = mock_run.call_args[0][0]
            assert cmd == ["ping", "-c", "1", "-W", "2000", "-D", "-s", "1400", "8.8.8.8"]


class TestRouteAdapters:
    def test_windows_route_adapter_commands(self):
        import ipaddress

        from src.platform.windows.route import WindowsRouteAdapter

        adapter = WindowsRouteAdapter()
        with patch.object(adapter, "_run", return_value=True) as mock_run:
            assert adapter.add_host_route("1.2.3.4", "192.168.1.1") is True
            mock_run.assert_called_with(
                ["route", "add", "1.2.3.4", "mask", "255.255.255.255", "192.168.1.1", "metric", "1"]
            )

            assert adapter.delete_host_route("1.2.3.4") is True
            mock_run.assert_called_with(["route", "delete", "1.2.3.4"])

            net = ipaddress.ip_network("192.168.0.0/16")
            assert adapter.add_cidr_route(net, "192.168.1.1") is True
            mock_run.assert_called_with(
                ["route", "add", "192.168.0.0", "mask", "255.255.0.0", "192.168.1.1", "metric", "1"]
            )

            assert adapter.delete_cidr_route(net) is True
            mock_run.assert_called_with(["route", "delete", "192.168.0.0"])

    def test_macos_route_adapter_commands(self):
        import ipaddress

        from src.platform.macos.route import MacosRouteAdapter

        adapter = MacosRouteAdapter()
        with patch.object(adapter, "_run", return_value=True) as mock_run:
            assert adapter.add_host_route("1.2.3.4", "192.168.1.1") is True
            mock_run.assert_called_with(["route", "-n", "add", "-host", "1.2.3.4", "192.168.1.1"])

            assert adapter.delete_host_route("1.2.3.4") is True
            mock_run.assert_called_with(["route", "-n", "delete", "-host", "1.2.3.4"])

            net = ipaddress.ip_network("10.0.0.0/8")
            assert adapter.add_cidr_route(net, "192.168.1.1") is True
            mock_run.assert_called_with(["route", "-n", "add", "-net", "10.0.0.0/8", "192.168.1.1"])

            assert adapter.delete_cidr_route(net) is True
            mock_run.assert_called_with(["route", "-n", "delete", "-net", "10.0.0.0/8"])

    def test_linux_route_adapter_commands(self):
        import ipaddress

        from src.platform.linux.route import LinuxRouteAdapter

        adapter = LinuxRouteAdapter()
        with patch.object(adapter, "_run", return_value=True) as mock_run:
            assert adapter.add_host_route("1.2.3.4", "192.168.1.1") is True
            mock_run.assert_called_with(["ip", "route", "add", "1.2.3.4", "via", "192.168.1.1"])

            assert adapter.delete_host_route("1.2.3.4") is True
            mock_run.assert_called_with(["ip", "route", "del", "1.2.3.4"])

            net = ipaddress.ip_network("172.16.0.0/12")
            assert adapter.add_cidr_route(net, "192.168.1.1") is True
            mock_run.assert_called_with(["ip", "route", "add", "172.16.0.0/12", "via", "192.168.1.1"])

            assert adapter.delete_cidr_route(net) is True
            mock_run.assert_called_with(["ip", "route", "del", "172.16.0.0/12"])


class TestConstants:
    def test_tun_adapter_name_defined(self):
        assert TUN_ADAPTER_NAME == "xenray-tun"

    def test_interface_contracts_exist(self):
        # Placeholder to keep the module deterministic.
        assert ITunDnsConfigurator is not None
