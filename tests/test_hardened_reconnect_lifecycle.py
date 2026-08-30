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
