"""Regression tests for SingboxService TUN readiness probe and platform INetworkAdapter.

Covers:
1. INetworkAdapter.is_interface_ready on Windows and POSIX.
2. SingboxService._wait_for_tun_ready delegation to INetworkAdapter.
3. Delayed TUN readiness (simulating Wintun driver initialization lag).
4. Unavailable or incorrect TUN interface / gateway (timeout & warning).
5. Genuine sing-box process startup failure (immediate abort without loop).
6. Clean abort in SingboxService.start() when sing-box dies during TUN wait.
7. Historical reproduction of legacy CIDR socket failure.
"""

from __future__ import annotations

import socket
from collections import namedtuple
from unittest.mock import MagicMock, patch

import pytest

from src.core.constants import TUN_GATEWAY_IPV4
from src.platform.posix import PosixNetworkAdapter
from src.platform.windows.network import WindowsNetworkAdapter
from src.services.core_engines.singbox_service import SingboxService

# Lightweight mocks mimicking psutil return structures
SnicAddr = namedtuple("snicaddr", ["family", "address", "netmask", "broadcast", "ptp"])
SnicStats = namedtuple("snicstats", ["isup", "duplex", "speed", "mtu", "flags"])


@pytest.fixture
def service():
    with patch("src.utils.process_utils.ProcessUtils.is_running", return_value=True):
        svc = SingboxService()
    svc._proc = MagicMock()
    svc._proc.is_running.return_value = True
    svc._proc.pid = 1234
    return svc


class TestPlatformNetworkAdapterInterfaceReady:
    """Tests for INetworkAdapter.is_interface_ready implementations."""

    def test_windows_adapter_is_interface_ready_success(self):
        adapter = WindowsNetworkAdapter()
        mock_addrs = {
            "SINGTUN": [
                SnicAddr(family=socket.AF_INET, address="10.0.0.1", netmask="255.255.0.0", broadcast=None, ptp=None),
            ]
        }
        mock_stats = {
            "SINGTUN": SnicStats(isup=True, duplex=2, speed=4294, mtu=1500, flags=""),
        }
        with (
            patch("psutil.net_if_addrs", return_value=mock_addrs),
            patch("psutil.net_if_stats", return_value=mock_stats),
        ):
            assert adapter.is_interface_ready("SINGTUN", "10.0.0.1") is True
            # Case-insensitivity & aliases
            assert adapter.is_interface_ready("singtun", "10.0.0.1") is True
            assert adapter.is_interface_ready("SINGTUN", "10.0.0.1/16") is True

    def test_windows_adapter_is_interface_ready_missing(self):
        adapter = WindowsNetworkAdapter()
        with (
            patch("psutil.net_if_addrs", return_value={"Ethernet": []}),
            patch("psutil.net_if_stats", return_value={}),
        ):
            assert adapter.is_interface_ready("SINGTUN", "10.0.0.1") is False

    def test_windows_adapter_is_interface_ready_wrong_ip(self):
        adapter = WindowsNetworkAdapter()
        mock_addrs = {
            "SINGTUN": [
                SnicAddr(
                    family=socket.AF_INET, address="192.168.1.1", netmask="255.255.255.0", broadcast=None, ptp=None
                ),
            ]
        }
        with (
            patch("psutil.net_if_addrs", return_value=mock_addrs),
            patch(
                "psutil.net_if_stats",
                return_value={"SINGTUN": SnicStats(isup=True, duplex=2, speed=4294, mtu=1500, flags="")},
            ),
        ):
            assert adapter.is_interface_ready("SINGTUN", "10.0.0.1") is False

    def test_windows_adapter_is_interface_ready_down(self):
        adapter = WindowsNetworkAdapter()
        mock_addrs = {
            "SINGTUN": [
                SnicAddr(family=socket.AF_INET, address="10.0.0.1", netmask="255.255.0.0", broadcast=None, ptp=None),
            ]
        }
        mock_stats = {
            "SINGTUN": SnicStats(isup=False, duplex=2, speed=0, mtu=1500, flags=""),
        }
        with (
            patch("psutil.net_if_addrs", return_value=mock_addrs),
            patch("psutil.net_if_stats", return_value=mock_stats),
        ):
            assert adapter.is_interface_ready("SINGTUN", "10.0.0.1") is False

    def test_posix_adapter_is_interface_ready(self):
        adapter = PosixNetworkAdapter()
        mock_addrs = {
            "tun0": [
                SnicAddr(family=socket.AF_INET, address="10.0.0.1", netmask="255.255.0.0", broadcast=None, ptp=None),
            ]
        }
        mock_stats = {
            "tun0": SnicStats(isup=True, duplex=2, speed=10, mtu=1420, flags=""),
        }
        with (
            patch("psutil.net_if_addrs", return_value=mock_addrs),
            patch("psutil.net_if_stats", return_value=mock_stats),
        ):
            assert adapter.is_interface_ready("tun0", "10.0.0.1") is True


class TestSingboxTunReadyRegression:
    """Regression test suite for SingboxService TUN interface readiness."""

    def test_reproduce_legacy_failure_path(self):
        """Document that passing TUN_GATEWAY_IPV4 ('10.0.0.1/16') to socket fails with gaierror."""
        assert "/" in TUN_GATEWAY_IPV4, "TUN_GATEWAY_IPV4 must contain CIDR prefix for this test"
        with pytest.raises(socket.gaierror):
            socket.create_connection((TUN_GATEWAY_IPV4, 80), timeout=0.1)

    def test_tun_ready_success_via_adapter(self, service):
        """TUN interface readiness delegates to get_network_adapter().is_interface_ready."""
        mock_adapter = MagicMock()
        mock_adapter.is_interface_ready.return_value = True

        with (
            patch("src.services.core_engines.singbox_service.get_network_adapter", return_value=mock_adapter),
            patch("src.utils.platform_utils.PlatformUtils.get_tun_interface_name", return_value="SINGTUN"),
        ):
            assert service._wait_for_tun_ready(timeout=1.0, poll_interval=0.05) is True
            mock_adapter.is_interface_ready.assert_called_once_with("SINGTUN", "10.0.0.1")

    def test_tun_ready_delayed_readiness(self, service):
        """Simulates Wintun creation latency: adapter not ready on first 2 attempts, ready on attempt 3."""
        mock_adapter = MagicMock()
        mock_adapter.is_interface_ready.side_effect = [False, False, True]

        with (
            patch("src.services.core_engines.singbox_service.get_network_adapter", return_value=mock_adapter),
            patch("src.utils.platform_utils.PlatformUtils.get_tun_interface_name", return_value="SINGTUN"),
        ):
            assert service._wait_for_tun_ready(timeout=1.0, poll_interval=0.02) is True
            assert mock_adapter.is_interface_ready.call_count == 3

    def test_tun_ready_timeout_via_adapter(self, service):
        """Interface never becomes ready: times out, logs warning, returns False."""
        mock_adapter = MagicMock()
        mock_adapter.is_interface_ready.return_value = False

        with (
            patch("src.services.core_engines.singbox_service.get_network_adapter", return_value=mock_adapter),
            patch("src.utils.platform_utils.PlatformUtils.get_tun_interface_name", return_value="SINGTUN"),
        ):
            assert service._wait_for_tun_ready(timeout=0.1, poll_interval=0.03) is False

    def test_tun_ready_genuine_process_startup_failure(self, service):
        """Sing-box crashes on startup: _wait_for_tun_ready immediately aborts without looping."""
        service._proc.is_running.return_value = False
        mock_adapter = MagicMock()

        with patch("src.services.core_engines.singbox_service.get_network_adapter", return_value=mock_adapter):
            result = service._wait_for_tun_ready(timeout=2.0, poll_interval=0.1)
            assert result is False
            mock_adapter.is_interface_ready.assert_not_called()

    def test_start_aborts_cleanly_on_process_death_during_tun_wait(self, service):
        """SingboxService.start() cleans up and returns None if process dies."""
        service._proc.pid = 999
        service._proc.is_running.return_value = False

        with (
            patch("src.platform.factory._is_windows", return_value=True),
            patch(
                "src.platform.windows.network.WindowsNetworkAdapter.get_primary_interface",
                return_value=("Wi-Fi", "192.168.1.10", "192.168.1.0/24", "192.168.1.1"),
            ),
            patch("src.platform.windows.settings._suppress_smhr"),
            patch.object(service, "_wait_for_xray_ready", return_value=True),
            patch.object(service, "_write_config_and_start", return_value=True),
            patch.object(service._route_manager, "setup_routes"),
            patch.object(service._route_manager, "cleanup_routes") as mock_cleanup,
        ):
            pid = service.start(xray_socks_port=10805)
            assert pid is None
            mock_cleanup.assert_called_once()
