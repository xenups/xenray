import unittest
from unittest.mock import Mock, patch

from src.core.connection_orchestrator import ConnectionOrchestrator
from src.services.legacy_config_service import LegacyConfigService
from src.services.xray_config_processor import XrayConfigProcessor


class TestLegacyConfigService(unittest.TestCase):
    def setUp(self):
        self.mock_processor = Mock(spec=XrayConfigProcessor)
        self.mock_processor.SUPPORTED_PROTOCOLS = ["vless", "vmess", "trojan"]
        self.service = LegacyConfigService(self.mock_processor)

    def test_detect_legacy_splithttp(self):
        config = {
            "outbounds": [{
                "streamSettings": {"network": "splithttp"}
            }]
        }
        self.assertTrue(self.service.is_legacy(config))

    def test_migrate_splithttp_to_xhttp(self):
        config = {
            "outbounds": [{
                "protocol": "vless",
                "streamSettings": {
                    "network": "splithttp",
                    "splithttpSettings": {"host": "example.com"}
                }
            }]
        }
        migrated = self.service.migrate_config(config)
        stream = migrated["outbounds"][0]["streamSettings"]
        self.assertEqual(stream["network"], "xhttp")
        self.assertIn("xhttpSettings", stream)
        self.assertEqual(stream["xhttpSettings"]["host"], "example.com")
        self.assertNotIn("splithttpSettings", stream)

    def test_migrate_invalid_security_and_network(self):
        config = {
            "outbounds": [{
                "protocol": "vless",
                "streamSettings": {
                    "network": "invalid_net",
                    "security": "invalid_sec"
                }
            }]
        }
        migrated = self.service.migrate_config(config)
        stream = migrated["outbounds"][0]["streamSettings"]
        self.assertEqual(stream["network"], "tcp")
        self.assertEqual(stream["security"], "none")

    def test_fill_transport_defaults(self):
        config = {
            "outbounds": [{
                "protocol": "vless",
                "settings": {"vnext": [{"address": "server.com", "port": 443}]},
                "streamSettings": {
                    "network": "ws",
                    "security": "tls"
                }
            }]
        }
        # Mock _get_server_object since it's used in _fill_transport_defaults
        self.mock_processor._get_server_object.return_value = {"address": "server.com"}

        migrated = self.service.migrate_config(config)
        stream = migrated["outbounds"][0]["streamSettings"]

        self.assertEqual(stream["wsSettings"]["path"], "/")
        self.assertEqual(stream["wsSettings"]["host"], "server.com")
        self.assertEqual(stream["tlsSettings"]["serverName"], "server.com")

    def test_non_legacy_ensures_tag(self):
        config = {
            "outbounds": [{
                "protocol": "vless",
                "streamSettings": {"network": "ws", "security": "tls"}
            }]
        }
        migrated = self.service.migrate_config(config)
        self.assertEqual(migrated["outbounds"][0]["tag"], "proxy")
        self.assertEqual(migrated["outbounds"][0]["streamSettings"]["network"], "ws")


class TestOrchestratorFallback(unittest.TestCase):
    def setUp(self):
        self.mock_config_manager = Mock()
        self.mock_config_processor = Mock()
        self.mock_network_validator = Mock()
        self.mock_xray_processor = Mock()
        self.mock_routing_manager = Mock()
        self.mock_xray_service = Mock()
        self.mock_singbox_service = Mock()
        self.mock_legacy_service = Mock()

        # Default mock returns
        self.mock_network_validator.check_internet_connection.return_value = True
        self.mock_xray_processor.process_config.side_effect = lambda x: x
        self.mock_xray_processor.get_socks_port.return_value = 10805

        self.orchestrator = ConnectionOrchestrator(
            self.mock_config_manager,
            self.mock_config_processor,
            self.mock_network_validator,
            self.mock_xray_processor,
            self.mock_routing_manager,
            self.mock_xray_service,
            self.mock_singbox_service,
            self.mock_legacy_service,
            None,
            None
        )

    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    @patch("json.dump")
    @patch("src.services.connection_tester.ConnectionTester.test_connection_sync")
    def test_fallback_flow(self, mock_test, mock_json, mock_file):
        """Verify that orchestrator falls back to original if migrated fails."""
        legacy_config = {"outbounds": [{"protocol": "vless", "network": "splithttp"}]}
        migrated_config = {"outbounds": [{"protocol": "vless", "network": "xhttp"}]}

        self.mock_config_manager.load_config.return_value = (legacy_config, None)
        self.mock_legacy_service.is_legacy.return_value = True
        self.mock_legacy_service.migrate_config.return_value = migrated_config

        # First attempt (migrated) fails, second (original) succeeds
        mock_test.side_effect = [
            (False, "fail", None),  # Migrated config test
            (True, "100ms", None)   # Original config test
        ]

        self.mock_xray_service.start.return_value = 1234  # PID

        success, info = self.orchestrator.establish_connection("dummy_path", "proxy")

        self.assertTrue(success)
        # Verify xray was started twice
        self.assertEqual(self.mock_xray_service.start.call_count, 2)
        # Verify teardown was called for failed attempt
        self.mock_xray_service.stop.assert_called()


if __name__ == "__main__":
    unittest.main()
