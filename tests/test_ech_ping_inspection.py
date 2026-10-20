"""Regression tests for Ping / Latency testing and Connection Inspection with ECH enabled."""

from __future__ import annotations

import json
import os
import time
from unittest.mock import MagicMock, patch

from src.core.event_bus import TOPIC_INSPECTION_BATCH_COMPLETED, TOPIC_SERVER_INSPECTED, event_bus
from src.core.parsers.binary_parser_adapter import LibXrayParserAdapter
from src.core.parsers.vless import VlessParser
from src.services.connection.connection_tester import ConnectionTester
from src.services.connection.server_inspector import ServerInspector

# Fully synthetic ECH profile config fixture
SYNTHETIC_ECH_LINK = (
    "vless://00000000-0000-0000-0000-000000000001@server.example.org:443"
    "?encryption=none&security=tls&sni=sni.example.org"
    "&fp=chrome&alpn=h2%2Chttp%2F1.1&ech=h2c%3A%2F%2F1.1.1.1%2Fdns-query"
    "&echOutbound=%7B%22tag%22%3A%22tls-repack-dns%22%2C%22protocol%22%3A%22direct%22%2C"
    "%22settings%22%3A%7B%22redirect%22%3A%221.1.1.1%3A443%22%7D%2C%22streamSettings%22%3A%7B"
    "%22security%22%3A%22tls%22%2C%22tlsSettings%22%3A%7B%22serverName%22%3A%22www.example.com%22%7D%7D%7D"
    "&type=xhttp&host=host.example.org&path=%2Fcalling&mode=auto#Synthetic-ECH-Node"
)


def _wait_for(condition, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


class TestEchPingRegression:
    """Regression tests for Ping and Latency testing with ECH-enabled profiles."""

    def test_temp_config_preserves_ech_outbound(self):
        """Verify that _create_temp_config preserves auxiliary outbounds like tls-repack-dns."""
        parsed = VlessParser.parse(SYNTHETIC_ECH_LINK)
        profile_config = parsed["config"]
        target = profile_config["outbounds"][0]
        extras = [o for o in profile_config["outbounds"] if o is not target and o.get("tag") not in ["direct", "block"]]

        port = ConnectionTester._find_free_port()
        config_path = ConnectionTester._create_temp_config(port, target, extra_outbounds=extras)
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                temp_cfg = json.load(f)

            tags = [o.get("tag") for o in temp_cfg["outbounds"]]
            assert "proxy" in tags
            assert "tls-repack-dns" in tags
            assert "direct" in tags

            # Verify that dialerProxy in primary outbound matches the auxiliary outbound
            dialer = target["streamSettings"]["tlsSettings"]["echSockopt"]["dialerProxy"]
            assert dialer == "tls-repack-dns"
            assert dialer in tags

            # Verify Xray core accepts this temporary configuration
            is_valid, err = LibXrayParserAdapter.validate_config(temp_cfg)
            assert is_valid is True, f"Temp config validation failed: {err}"
        finally:
            if os.path.exists(config_path):
                os.remove(config_path)

    def test_test_connection_sync_extracts_and_passes_extra_outbounds(self):
        """Verify that test_connection_sync extracts auxiliary outbounds from profile_config."""
        parsed = VlessParser.parse(SYNTHETIC_ECH_LINK)
        profile_config = parsed["config"]

        created_configs = []
        orig_create = ConnectionTester._create_temp_config

        def spy_create(listen_port, outbound_config, extra_outbounds=None):
            created_configs.append((outbound_config, extra_outbounds))
            return orig_create(listen_port, outbound_config, extra_outbounds=extra_outbounds)

        with patch.object(ConnectionTester, "_create_temp_config", side_effect=spy_create):
            with patch.object(ConnectionTester, "_probe_204", return_value=(True, 95)):
                with patch("subprocess.Popen") as mock_popen:
                    mock_proc = MagicMock()
                    mock_proc.poll.return_value = None
                    mock_popen.return_value = mock_proc

                    success, result, country = ConnectionTester.test_connection_sync(
                        profile_config, fetch_country=False
                    )

                    assert success is True
                    assert "95" in result
                    assert country is None

        assert len(created_configs) == 1
        target_ob, extra_obs = created_configs[0]
        assert target_ob.get("tag") == "proxy"
        assert extra_obs is not None
        assert any(o.get("tag") == "tls-repack-dns" for o in extra_obs)

    def test_ping_error_propagation_without_false_success(self):
        """Verify that when the probe fails, test_connection_sync returns failure cleanly."""
        parsed = VlessParser.parse(SYNTHETIC_ECH_LINK)
        profile_config = parsed["config"]

        with patch.object(ConnectionTester, "_probe_204", return_value=(False, 0)):
            with patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.poll.return_value = None
                mock_popen.return_value = mock_proc

                success, result, country = ConnectionTester.test_connection_sync(profile_config)
                assert success is False
                assert country is None
                assert result != ""

    def test_ping_invalid_config_handled_cleanly(self):
        """Verify that invalid or missing outbound configs fail safely."""
        success, result, country = ConnectionTester.test_connection_sync({})
        assert success is False
        assert country is None

    def test_ping_subprocess_failure_handled_cleanly(self):
        """Verify that core failure during warm-up is reported cleanly."""
        parsed = VlessParser.parse(SYNTHETIC_ECH_LINK)
        profile_config = parsed["config"]

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = 1  # Core exited prematurely
            mock_popen.return_value = mock_proc

            success, result, country = ConnectionTester.test_connection_sync(profile_config)
            assert success is False
            assert country is None


class TestEchInspectionRegression:
    """Regression tests for Server / Connection Inspection with ECH-enabled profiles."""

    def test_inspection_success_with_ech_profile(self):
        """Verify that ServerInspector successfully inspects ECH profile and publishes event."""
        parsed = VlessParser.parse(SYNTHETIC_ECH_LINK)
        profile = {
            "id": "ech-server-1",
            "name": "Synthetic-ECH-Node",
            "config": parsed["config"],
        }

        received_events = []
        event_bus.subscribe(TOPIC_SERVER_INSPECTED, lambda d: received_events.append(d))

        try:
            with patch.object(
                ConnectionTester,
                "test_connection_sync",
                return_value=(
                    True,
                    "Latency: 110ms",
                    {"country_code": "US", "country_name": "United States", "city": "Dallas"},
                ),
            ):
                inspector = ServerInspector()
                inspector.inspect(profile)

                assert _wait_for(lambda: bool(received_events))

            event = received_events[-1]
            assert event["server_id"] == "ech-server-1"
            assert event["success"] is True
            assert event["ping"] == 110
            assert event["location"]["country_code"] == "US"
            assert event["location"]["city"] == "Dallas"
        finally:
            event_bus.unsubscribe(TOPIC_SERVER_INSPECTED, lambda d: received_events.append(d))

    def test_inspection_failure_handled_cleanly(self):
        """Verify that failed inspection publishes safe failure event without exceptions."""
        parsed = VlessParser.parse(SYNTHETIC_ECH_LINK)
        profile = {
            "id": "ech-server-fail",
            "name": "Synthetic-ECH-Node",
            "config": parsed["config"],
        }

        received_events = []
        event_bus.subscribe(TOPIC_SERVER_INSPECTED, lambda d: received_events.append(d))

        try:
            with patch.object(
                ConnectionTester,
                "test_connection_sync",
                return_value=(False, "Connection Error", None),
            ):
                inspector = ServerInspector()
                inspector.inspect(profile)

                assert _wait_for(lambda: bool(received_events))

            event = received_events[-1]
            assert event["server_id"] == "ech-server-fail"
            assert event["success"] is False
            assert event["ping"] is None
            assert event["location"] == {}
        finally:
            event_bus.unsubscribe(TOPIC_SERVER_INSPECTED, lambda d: received_events.append(d))

    def test_inspection_batch_with_ech_profiles(self):
        """Verify batch inspection with multiple ECH profiles completes properly."""
        parsed = VlessParser.parse(SYNTHETIC_ECH_LINK)
        profiles = [{"id": f"ech-{i}", "name": f"ECH-{i}", "config": parsed["config"]} for i in range(3)]

        received_events = []
        batch_events = []
        event_bus.subscribe(TOPIC_SERVER_INSPECTED, lambda d: received_events.append(d))
        event_bus.subscribe(TOPIC_INSPECTION_BATCH_COMPLETED, lambda d: batch_events.append(d))

        try:
            with patch.object(
                ConnectionTester,
                "test_connection_sync",
                return_value=(True, "80ms", {"country_code": "DE", "country_name": "Germany"}),
            ):
                inspector = ServerInspector()
                inspector.inspect_batch(profiles)

                assert _wait_for(lambda: len(received_events) >= 3 and bool(batch_events))

            assert len(received_events) >= 3
            assert {e["server_id"] for e in received_events} == {f"ech-{i}" for i in range(3)}
            assert batch_events[-1]["canceled"] is False
        finally:
            event_bus.unsubscribe(TOPIC_SERVER_INSPECTED, lambda d: received_events.append(d))
            event_bus.unsubscribe(TOPIC_INSPECTION_BATCH_COMPLETED, lambda d: batch_events.append(d))

    def test_inspection_cancellation(self):
        """Verify cancelling in-flight inspections publishes batch completed with canceled=True."""
        batch_events = []
        event_bus.subscribe(TOPIC_INSPECTION_BATCH_COMPLETED, lambda d: batch_events.append(d))

        try:
            inspector = ServerInspector()
            inspector.cancel_all_inspections()

            assert _wait_for(lambda: bool(batch_events))
            assert batch_events[-1]["canceled"] is True
        finally:
            event_bus.unsubscribe(TOPIC_INSPECTION_BATCH_COMPLETED, lambda d: batch_events.append(d))
