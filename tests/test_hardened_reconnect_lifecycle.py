"""Automated unit and integration tests for hardened XenRay network and auto-reconnect architecture (Phases 1-5)."""

import time
from collections import deque
from unittest.mock import MagicMock, patch

import pytest

from src.core.singbox.builders.route_config_builder import RouteConfigBuilder
from src.platform.windows.network import (
    _is_physical_iftype,
    _is_virtual_adapter,
    get_physical_nic_candidates,
)
from src.services.core_engines.config_patcher import ConfigPatcher
from src.services.monitoring.active_connectivity_monitor import ActiveConnectivityMonitor
from src.services.monitoring.auto_reconnect_service import AutoReconnectService
from src.services.monitoring.passive_log_monitor import PassiveLogMonitor


class TestPhase1CoreConfig:
    """Test Phase 1: Core Configuration Refactoring."""

    def test_sockopt_hardening_injection(self):
        patcher = ConfigPatcher()
        outbound = {
            "protocol": "vmess",
            "settings": {"vnext": [{"address": "1.2.3.4", "port": 443}]},
            "streamSettings": {"network": "tcp"},
        }
        patcher._apply_sockopt_hardening(outbound)
        sockopt = outbound["streamSettings"]["sockopt"]
        # v2.4.1-PROD: 10s idle + (10 * 3s) = 40s Winsock kernel drop time
        assert sockopt["tcpKeepAliveInterval"] == 3
        assert sockopt["tcpKeepAliveIdle"] == 10
        assert sockopt["tcpNoDelay"] is True

    def test_route_builder_primary_anti_loop_ip_bypass(self):
        builder = RouteConfigBuilder()
        rules = [
            {"protocol": ["dns"], "outbound": "dns-out"},
            {"ip_cidr": ["8.8.8.8/32"], "outbound": "direct"},
        ]
        dns_rules = []
        builder.inject_loop_breakers(
            rules=rules,
            dns_rules=dns_rules,
            proxy_ips=["198.51.100.1"],
            proxy_domains=[],
            sni_connect_ip=None,
        )
        # Server IP rule MUST be at index 0 as PRIMARY strategy
        primary_rule = rules[0]
        assert primary_rule["outbound"] == "direct"
        assert primary_rule.get("ip_cidr") == "198.51.100.1/32"


class TestPhase2ActiveAdaptiveProbing:
    """Test Phase 2: Active & Adaptive Probing Redesign."""

    def test_lazy_throughput_gating_suppresses_probe(self):
        monitor = ActiveConnectivityMonitor()
        monitor._last_total_bytes = 1000

        with patch("psutil.net_io_counters") as mock_io:
            # 2048 bytes transferred > 1024 bytes threshold
            mock_io.return_value = MagicMock(bytes_recv=2000, bytes_sent=1048)
            assert monitor._check_traffic_flow() is True
            assert monitor._last_total_bytes == 3048

    def test_socks5_tunnel_handshake_atyp3_payload(self):
        monitor = ActiveConnectivityMonitor()
        with patch("socket.create_connection") as mock_conn:
            mock_sock = MagicMock()
            mock_conn.return_value.__enter__.return_value = mock_sock
            # SOCKS5 greeting response (0x05, 0x00) + connect response (0x05, 0x00, ...)
            mock_sock.recv.side_effect = [b"\x05\x00", b"\x05\x00\x00\x01\x01\x01\x01\x01\x00\x50"]

            assert monitor._probe_socks_tunnel(10805) is True
            # Verify greeting sent
            mock_sock.sendall.assert_any_call(b"\x05\x01\x00")
            # Verify CONNECT to cp.cloudflare.com:80 via ATYP=0x03 sent (zero local DNS leak)
            expected_connect = b"\x05\x01\x00\x03\x11cp.cloudflare.com\x00\x50"
            mock_sock.sendall.assert_any_call(expected_connect)


class TestPhase3PhysicalNICFiltering:
    """Test Phase 3: Physical Network & Interface Lifecycle."""

    def test_virtual_adapter_filtering(self):
        assert _is_virtual_adapter("XenRay-TUN", "XenRay Virtual Network Adapter") is True
        assert _is_virtual_adapter("TAP-Windows Adapter V9", "TAP-Windows") is True
        assert _is_virtual_adapter("WireGuard Tunnel", "WireGuard Virtual Network Adapter") is True
        assert _is_virtual_adapter("Tailscale", "Tailscale Tunnel") is True
        assert _is_virtual_adapter("vEthernet (Default Switch)", "Hyper-V Virtual Ethernet Adapter") is True
        assert _is_virtual_adapter("sing-box TUN", "sing-box Virtual Adapter") is True
        assert _is_virtual_adapter("Intel(R) Wi-Fi 6 AX201 160MHz", "Intel Physical Wi-Fi") is False
        assert _is_virtual_adapter("Realtek PCIe GbE Family Controller", "Realtek Ethernet") is False


class TestPhase4AutoReconnectEngine:
    """Test Phase 4: Auto-Reconnect Engine Hardening."""

    def test_exponential_backoff_formula_and_jitter(self):
        service = AutoReconnectService(
            network_validator=MagicMock(),
            config_loader=MagicMock(),
            connection_tester=MagicMock(),
            connect_fn=MagicMock(),
            event_emitter=MagicMock(),
        )
        # Attempt 1: Immediate trigger (0s delay, not part of backoff math)
        service._consecutive_failures = 0
        assert service._backoff_seconds() == 0.0

        # Attempt 2: 2.0 * 2^(2 - 2) = 2s ± 20% (1.6s - 2.4s)
        service._consecutive_failures = 1
        b2 = service._backoff_seconds()
        assert 1.6 <= b2 <= 2.4

        # Attempt 3: 2.0 * 2^(3 - 2) = 4s ± 20% (3.2s - 4.8s)
        service._consecutive_failures = 2
        b3 = service._backoff_seconds()
        assert 3.2 <= b3 <= 4.8

        # Attempt 4: 2.0 * 2^(4 - 2) = 8s ± 20% (6.4s - 9.6s)
        service._consecutive_failures = 3
        b4 = service._backoff_seconds()
        assert 6.4 <= b4 <= 9.6

        # Attempt 5: 2.0 * 2^(5 - 2) = 16s ± 20% (12.8s - 19.2s)
        service._consecutive_failures = 4
        b5 = service._backoff_seconds()
        assert 12.8 <= b5 <= 19.2

    def test_max_attempts_ceiling_transitions_to_paused(self):
        emitted = []
        service = AutoReconnectService(
            network_validator=MagicMock(),
            config_loader=MagicMock(),
            connection_tester=MagicMock(),
            connect_fn=MagicMock(),
            event_emitter=lambda event, data: emitted.append((event, data)),
        )
        service.start_session(1)
        service._consecutive_failures = 5

        result = service.handle_failure({"file": "test.json", "mode": "vpn"}, session_id=1)
        assert result is False
        events = [e[0] for e in emitted]
        assert "reconnect_paused" in events
        service.cancel()

    def test_reset_backoff_on_interface_change(self):
        service = AutoReconnectService(
            network_validator=MagicMock(),
            config_loader=MagicMock(),
            connection_tester=MagicMock(),
            connect_fn=MagicMock(),
            event_emitter=MagicMock(),
        )
        service._consecutive_failures = 4
        service.reset_backoff(reason="interface_change")
        assert service._consecutive_failures == 0


class TestPhase5SlidingWindowLogAggregator:
    """Test Phase 5: Log Aggregator & Windowing."""

    def test_sliding_window_non_error_lines_do_not_reset(self):
        alerts = []
        monitor = PassiveLogMonitor(
            on_failure_callback=lambda payload: alerts.append(payload),
            log_files=[],
        )
        monitor.REQUIRED_FAILURE_LINES = 3
        monitor.start()

        err_line = "2026/01/01 [Warning] dial tcp 1.2.3.4:443: i/o timeout"
        info_line = "2026/01/01 [Info] proxying request to target"

        monitor._process_line(err_line)
        assert len(alerts) == 0
        monitor._process_line(info_line)  # Non-error line: must NOT clear failure window
        monitor._process_line(err_line)
        assert len(alerts) == 0
        monitor._process_line(info_line)
        monitor._process_line(err_line)  # 3rd failure line within 12s window

        time.sleep(0.2)  # wait for threadpool callback
        assert len(alerts) == 1
        monitor.stop()


class TestPhase6InterfaceWatcherDebounceAndFSM:
    """Test Phase 6: Interface Watcher Debounce, Filtering, and FSM Hot Transitions."""

    def _make_watcher(self, monkeypatch, nic_state_holder):
        """Helper: build a watcher with a monkeypatched nic candidate function."""
        from src.platform.windows.network import WindowsInterfaceWatcher
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state_holder[0],
        )
        callbacks = []
        watcher = WindowsInterfaceWatcher(callback=lambda: callbacks.append(True))
        watcher.DEBOUNCE_SECONDS = 0.05
        return watcher, callbacks

    def test_interface_watcher_suppresses_unchanged_physical_nic(self, monkeypatch):
        """TUN/virtual adapter mutations must NOT fire the callback (echo suppression)."""
        nic_state = [
            {
                "name": "Ethernet",
                "guid": "{11111111-2222-3333-4444-555555555555}",
                "ip": "192.168.1.100",
                "gateway": "192.168.1.1",
                "ifindex": 5,
            }
        ]
        watcher, callbacks = self._make_watcher(monkeypatch, [nic_state])
        # Establish baseline
        watcher._last_physical_state = watcher._get_current_physical_state()

        # Simulate debounced handler firing on internal route/TUN mutation (state unchanged)
        watcher._debounced_handler()
        assert len(callbacks) == 0, "Callback must be suppressed when physical NIC and gateway are unchanged"

    def test_interface_watcher_fires_on_cable_unplug(self, monkeypatch):
        """CORE BUG FIX: When the network cable is unplugged, nic candidates returns [].
        The watcher must fire the callback (transition to _NETWORK_DOWN sentinel)."""
        from src.platform.windows.network import WindowsInterfaceWatcher

        nic_state = [[
            {
                "name": "Ethernet",
                "guid": "{11111111-2222-3333-4444-555555555555}",
                "ip": "192.168.1.100",
                "gateway": "192.168.1.1",
                "ifindex": 5,
            }
        ]]
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state[0],
        )
        callbacks = []
        watcher = WindowsInterfaceWatcher(callback=lambda: callbacks.append(True))
        watcher.DEBOUNCE_SECONDS = 0.05

        # Establish baseline with a valid NIC
        watcher._last_physical_state = watcher._get_current_physical_state()
        assert watcher._last_physical_state != WindowsInterfaceWatcher._NETWORK_DOWN

        # Simulate cable unplug: nic_state goes empty
        nic_state[0] = []
        watcher._debounced_handler()
        assert len(callbacks) == 1, (
            "Callback MUST fire when cable is unplugged (empty NIC list → _NETWORK_DOWN sentinel)"
        )
        # _last_physical_state must now be the down sentinel
        assert watcher._last_physical_state == WindowsInterfaceWatcher._NETWORK_DOWN

    def test_interface_watcher_fires_on_cable_reconnect(self, monkeypatch):
        """When network comes back after unplug, callback must fire (DOWN → valid state)."""
        from src.platform.windows.network import WindowsInterfaceWatcher

        nic_state = [[]]  # Start with cable unplugged
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state[0],
        )
        callbacks = []
        watcher = WindowsInterfaceWatcher(callback=lambda: callbacks.append(True))
        watcher.DEBOUNCE_SECONDS = 0.05
        # Baseline is NETWORK_DOWN (cable was already out at start)
        watcher._last_physical_state = WindowsInterfaceWatcher._NETWORK_DOWN

        # Cable plugged back in
        nic_state[0] = [
            {
                "name": "Ethernet",
                "guid": "{11111111-2222-3333-4444-555555555555}",
                "ip": "192.168.1.100",
                "gateway": "192.168.1.1",
                "ifindex": 5,
            }
        ]
        watcher._debounced_handler()
        assert len(callbacks) == 1, (
            "Callback MUST fire when cable is reconnected (_NETWORK_DOWN → valid adapter)"
        )
        assert watcher._last_physical_state != WindowsInterfaceWatcher._NETWORK_DOWN

    def test_interface_watcher_suppresses_repeated_down_events(self, monkeypatch):
        """Sustained disconnection must not fire repeated callbacks (DOWN stays DOWN)."""
        nic_state = [[]]
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state[0],
        )
        from src.platform.windows.network import WindowsInterfaceWatcher
        callbacks = []
        watcher = WindowsInterfaceWatcher(callback=lambda: callbacks.append(True))
        watcher.DEBOUNCE_SECONDS = 0.05
        # Baseline is already NETWORK_DOWN (persisted from previous call)
        watcher._last_physical_state = WindowsInterfaceWatcher._NETWORK_DOWN

        watcher._debounced_handler()
        assert len(callbacks) == 0, "Repeated DOWN→DOWN transitions must be suppressed"

    def test_interface_watcher_fires_when_physical_gateway_changes(self, monkeypatch):
        """WiFi handover (Ethernet→WiFi, different gateway) must fire the callback."""
        nic_state = [[
            {
                "name": "Ethernet",
                "guid": "{11111111-2222-3333-4444-555555555555}",
                "ip": "192.168.1.100",
                "gateway": "192.168.1.1",
                "ifindex": 5,
            }
        ]]
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state[0],
        )
        from src.platform.windows.network import WindowsInterfaceWatcher
        callbacks = []
        watcher = WindowsInterfaceWatcher(callback=lambda: callbacks.append(True))
        watcher.DEBOUNCE_SECONDS = 0.05
        watcher._last_physical_state = watcher._get_current_physical_state()

        # Physical link changes (e.g. Wi-Fi handover / new default gateway)
        nic_state[0] = [
            {
                "name": "Wi-Fi",
                "guid": "{99999999-8888-7777-6666-555555555555}",
                "ip": "10.0.0.50",
                "gateway": "10.0.0.1",
                "ifindex": 8,
            }
        ]
        watcher._debounced_handler()
        assert len(callbacks) == 1, "Callback must fire when physical NIC / gateway actually transitions"

    def test_connection_fsm_allows_hot_reconnect_from_connected(self):
        from src.core.fsm.connection_fsm import ConnectionFSM, ConnectionState

        fsm = ConnectionFSM()
        # Navigate to CONNECTED
        assert fsm.transition_to(ConnectionState.STARTING)
        assert fsm.transition_to(ConnectionState.PREPARING)
        assert fsm.transition_to(ConnectionState.CONNECTED)
        assert fsm.state == ConnectionState.CONNECTED

        # Hot reconnect: CONNECTED -> PREPARING must be allowed without warnings
        assert fsm.transition_to(ConnectionState.PREPARING)
        assert fsm.state == ConnectionState.PREPARING

        # Recovery to CONNECTED
        assert fsm.transition_to(ConnectionState.CONNECTED)
        assert fsm.state == ConnectionState.CONNECTED

        # Hot reconnect via STOPPING: CONNECTED -> STOPPING -> PREPARING
        assert fsm.transition_to(ConnectionState.STOPPING)
        assert fsm.transition_to(ConnectionState.PREPARING)
        assert fsm.transition_to(ConnectionState.CONNECTED)
        assert fsm.state == ConnectionState.CONNECTED


class TestPhase7LinkRecoveryBackoffReset:
    """Phase 7: Link Recovery Triggers Backoff Reset.

    Verifies the full lifecycle:
      reconnect_paused (failures > 0) -> _NETWORK_DOWN -> valid state
      -> auto_reconnect_service.reset_backoff() fires -> consecutive_failures == 0
    """

    def _make_watcher(self, monkeypatch, nic_state_holder):
        from src.platform.windows.network import WindowsInterfaceWatcher
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state_holder[0],
        )
        callbacks = []
        watcher = WindowsInterfaceWatcher(callback=lambda: callbacks.append(True))
        watcher.DEBOUNCE_SECONDS = 0.05
        return watcher, callbacks

    def test_link_restore_resets_backoff_and_clears_failures(self, monkeypatch):
        """DOWN -> valid transition MUST call reset_backoff(), zeroing consecutive_failures."""
        from src.platform.windows.network import WindowsInterfaceWatcher
        from src.services.monitoring.auto_reconnect_service import AutoReconnectService

        nic_state = [[]]  # Start: cable unplugged
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state[0],
        )

        svc = AutoReconnectService(
            network_validator=MagicMock(),
            config_loader=MagicMock(),
            connection_tester=MagicMock(),
            connect_fn=MagicMock(),
            event_emitter=MagicMock(),
        )
        svc._consecutive_failures = 5  # Simulate reconnect_paused

        def _on_link_change():
            """Mirrors ConnectionManager: reset backoff only on link recovery (DOWN->valid)."""
            if watcher._last_physical_state != watcher._NETWORK_DOWN:
                svc.reset_backoff(reason="interface_change")

        watcher = WindowsInterfaceWatcher(callback=_on_link_change)
        watcher._last_physical_state = watcher._NETWORK_DOWN  # Baseline: down

        # Cable reconnected
        nic_state[0] = [
            {
                "name": "Ethernet",
                "guid": "{AAAA-BBBB-CCCC-DDDD}",
                "ip": "192.168.1.100",
                "gateway": "192.168.1.1",
                "ifindex": 5,
            }
        ]
        watcher._debounced_handler()

        assert svc._consecutive_failures == 0, (
            "reset_backoff() must zero consecutive_failures on link recovery"
        )
        assert watcher._last_physical_state != watcher._NETWORK_DOWN

    def test_cable_unplug_does_not_reset_backoff(self, monkeypatch):
        """valid -> _NETWORK_DOWN fires callback but reset_backoff must NOT be called on DOWN."""
        from src.platform.windows.network import WindowsInterfaceWatcher
        from src.services.monitoring.auto_reconnect_service import AutoReconnectService

        nic_state = [[
            {
                "name": "Ethernet",
                "guid": "{AAAA-BBBB-CCCC-DDDD}",
                "ip": "192.168.1.100",
                "gateway": "192.168.1.1",
                "ifindex": 5,
            }
        ]]
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state[0],
        )

        svc = AutoReconnectService(
            network_validator=MagicMock(),
            config_loader=MagicMock(),
            connection_tester=MagicMock(),
            connect_fn=MagicMock(),
            event_emitter=MagicMock(),
        )
        svc._consecutive_failures = 3

        def _on_link_change():
            if watcher._last_physical_state != watcher._NETWORK_DOWN:
                svc.reset_backoff(reason="interface_change")

        watcher = WindowsInterfaceWatcher(callback=_on_link_change)
        watcher._last_physical_state = watcher._get_current_physical_state()

        # Cable unplugged
        nic_state[0] = []
        watcher._debounced_handler()

        # Callback fired but reset_backoff must NOT have been invoked (link went DOWN, not UP)
        assert watcher._last_physical_state == watcher._NETWORK_DOWN
        assert svc._consecutive_failures == 3, (
            "reset_backoff must NOT be called on link DOWN transitions"
        )

    def test_paused_service_backoff_zeroed_after_link_recovery(self, monkeypatch):
        """Integration: MAX consecutive failures (paused) -> link recovers -> failures zeroed."""
        from src.platform.windows.network import WindowsInterfaceWatcher
        from src.services.monitoring.auto_reconnect_service import AutoReconnectService

        nic_state = [[]]
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state[0],
        )
        svc = AutoReconnectService(
            network_validator=MagicMock(),
            config_loader=MagicMock(),
            connection_tester=MagicMock(),
            connect_fn=MagicMock(),
            event_emitter=MagicMock(),
        )
        svc._consecutive_failures = svc.MAX_CONSECUTIVE_ATTEMPTS  # fully paused

        def _on_link_change():
            if watcher._last_physical_state != watcher._NETWORK_DOWN:
                svc.reset_backoff(reason="interface_change")

        watcher = WindowsInterfaceWatcher(callback=_on_link_change)
        watcher._last_physical_state = watcher._NETWORK_DOWN

        nic_state[0] = [
            {
                "name": "Ethernet",
                "guid": "{AAAA-BBBB-CCCC-DDDD}",
                "ip": "10.20.30.40",
                "gateway": "10.20.30.1",
                "ifindex": 3,
            }
        ]
        watcher._debounced_handler()

        assert svc._consecutive_failures == 0, (
            "Fully-paused service must resume after link recovery resets backoff"
        )


class TestPhase8NetworkResilienceEdgeCases:
    """Phase 8: Rapid Flapping & Multi-Homed Resilience.

    1. Rapid valid->DOWN->valid within debounce window collapses to zero callbacks.
    2. Multi-homed failover (ETH drops, Wi-Fi stays) never triggers _NETWORK_DOWN.
    """

    # ------------------------------------------------------------------
    # Rapid Network Flapping
    # ------------------------------------------------------------------

    def test_rapid_flap_same_nic_collapses_to_zero_callbacks(self, monkeypatch):
        """valid -> DOWN -> valid (same NIC) within debounce window: 0 callbacks.

        When the link oscillates faster than DEBOUNCE_SECONDS, the OS fires
        NotifyIpInterfaceChange multiple times resetting the timer on each event.
        After the dust settles the handler fires ONCE and sees the current state
        matches the original baseline -> suppress.
        """
        from src.platform.windows.network import WindowsInterfaceWatcher

        ETH = {
            "name": "Ethernet",
            "guid": "{AAAA-0000}",
            "ip": "192.168.1.100",
            "gateway": "192.168.1.1",
            "ifindex": 5,
        }

        nic_state = [[ETH]]
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state[0],
        )

        callbacks = []
        watcher = WindowsInterfaceWatcher(callback=lambda: callbacks.append(True))
        watcher.DEBOUNCE_SECONDS = 0.05

        # Baseline: Ethernet is UP
        watcher._last_physical_state = watcher._get_current_physical_state()

        # Simulate OS event burst (rapid DOWN then UP before debounce fires):
        nic_state[0] = []     # OS event 1: link down  (timer reset, no handler yet)
        nic_state[0] = [ETH]  # OS event 2: link back up (timer reset again, no handler yet)

        # Single debounce handler invocation (after timer settles)
        watcher._debounced_handler()

        assert len(callbacks) == 0, (
            "Rapid valid->DOWN->valid flap within debounce window MUST collapse to 0 callbacks"
        )

    def test_rapid_flap_net_different_nic_produces_single_callback(self, monkeypatch):
        """valid A -> DOWN -> valid B (different NIC) within debounce: exactly 1 callback."""
        from src.platform.windows.network import WindowsInterfaceWatcher

        ETH = {
            "name": "Ethernet",
            "guid": "{AAAA-0000}",
            "ip": "192.168.1.100",
            "gateway": "192.168.1.1",
            "ifindex": 5,
        }
        WIFI = {
            "name": "Wi-Fi",
            "guid": "{BBBB-1111}",
            "ip": "10.0.0.50",
            "gateway": "10.0.0.1",
            "ifindex": 8,
        }

        nic_state = [[ETH]]
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state[0],
        )

        callbacks = []
        watcher = WindowsInterfaceWatcher(callback=lambda: callbacks.append(True))
        watcher.DEBOUNCE_SECONDS = 0.05

        # Baseline: Ethernet
        watcher._last_physical_state = watcher._get_current_physical_state()

        # OS burst: ETH->DOWN->WIFI (net result after debounce: WIFI is primary)
        nic_state[0] = []      # OS event 1: link down
        nic_state[0] = [WIFI]  # OS event 2: Wi-Fi comes up before debounce fires

        # Single debounce handler invocation
        watcher._debounced_handler()

        assert len(callbacks) == 1, (
            "ETH->DOWN->WIFI flap must yield exactly 1 callback for the net adapter change"
        )
        assert watcher._last_physical_state != watcher._NETWORK_DOWN
        assert watcher._last_physical_state[0] == WIFI["guid"]

    # ------------------------------------------------------------------
    # Multi-Homed Resilience
    # ------------------------------------------------------------------

    def test_multihomed_ethernet_drop_wifi_survives_no_network_down(self, monkeypatch):
        """ETH drops while Wi-Fi remains: one callback for adapter change, never _NETWORK_DOWN."""
        from src.platform.windows.network import WindowsInterfaceWatcher

        ETH = {
            "name": "Ethernet",
            "guid": "{ETH-GUID}",
            "ip": "192.168.1.100",
            "gateway": "192.168.1.1",
            "ifindex": 2,
            "metric": 5,
        }
        WIFI = {
            "name": "Wi-Fi",
            "guid": "{WIFI-GUID}",
            "ip": "10.0.0.50",
            "gateway": "10.0.0.1",
            "ifindex": 8,
            "metric": 50,
        }

        # Both adapters up, Ethernet is primary (lower metric -> sorted first)
        nic_state = [[ETH, WIFI]]
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state[0],
        )

        callbacks = []
        false_downs = []

        def _on_change():
            callbacks.append(True)
            if watcher._last_physical_state == watcher._NETWORK_DOWN:
                false_downs.append("FALSE_DOWN")

        watcher = WindowsInterfaceWatcher(callback=_on_change)
        watcher.DEBOUNCE_SECONDS = 0.05

        # Baseline: Ethernet is primary
        watcher._last_physical_state = watcher._get_current_physical_state()
        assert watcher._last_physical_state[0] == ETH["guid"]

        # Ethernet drops — only Wi-Fi remains
        nic_state[0] = [WIFI]
        watcher._debounced_handler()

        assert len(callbacks) == 1, "Ethernet failover to Wi-Fi must fire exactly one callback"
        assert len(false_downs) == 0, (
            "Multi-homed failover MUST NOT trigger _NETWORK_DOWN when Wi-Fi adapter survives"
        )
        assert watcher._last_physical_state[0] == WIFI["guid"], (
            "After Ethernet drop, Wi-Fi must become the tracked primary"
        )

    def test_multihomed_both_drop_signals_network_down(self, monkeypatch):
        """Both ETH and Wi-Fi drop simultaneously: _NETWORK_DOWN correctly signalled."""
        from src.platform.windows.network import WindowsInterfaceWatcher

        ETH = {
            "name": "Ethernet",
            "guid": "{ETH-GUID}",
            "ip": "192.168.1.100",
            "gateway": "192.168.1.1",
            "ifindex": 2,
            "metric": 5,
        }
        WIFI = {
            "name": "Wi-Fi",
            "guid": "{WIFI-GUID}",
            "ip": "10.0.0.50",
            "gateway": "10.0.0.1",
            "ifindex": 8,
            "metric": 50,
        }

        nic_state = [[ETH, WIFI]]
        monkeypatch.setattr(
            "src.platform.windows.network.get_physical_nic_candidates",
            lambda: nic_state[0],
        )

        callbacks = []
        watcher = WindowsInterfaceWatcher(callback=lambda: callbacks.append(True))
        watcher.DEBOUNCE_SECONDS = 0.05

        # Baseline: both up
        watcher._last_physical_state = watcher._get_current_physical_state()

        # Full outage: both adapters drop
        nic_state[0] = []
        watcher._debounced_handler()

        assert len(callbacks) == 1, "Full outage (all NICs drop) must fire exactly one callback"
        assert watcher._last_physical_state == watcher._NETWORK_DOWN, (
            "When ALL adapters are gone, watcher state must be _NETWORK_DOWN"
        )
